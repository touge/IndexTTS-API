import os
import json
import re
import time
import librosa
import torch
import torchaudio
from torch.nn.utils.rnn import pad_sequence
import warnings
from omegaconf import OmegaConf
from indextts.infer_v2 import IndexTTS2 as RefIndexTTS2, find_most_similar_cosine
from indextts.gpt.model_v2 import UnifiedVoice

# from src.core.indextts.utils.maskgct_utils import build_semantic_model, build_semantic_codec

from .utils.maskgct_utils import build_semantic_model, build_semantic_codec

from indextts.utils.checkpoint import load_checkpoint
from indextts.utils.front import TextNormalizer, TextTokenizer
from indextts.s2mel.modules.commons import load_checkpoint2, MyModel
from indextts.s2mel.modules.bigvgan import bigvgan
from indextts.s2mel.modules.campplus.DTDNN import CAMPPlus
from indextts.s2mel.modules.audio import mel_spectrogram
from transformers import AutoTokenizer, SeamlessM4TFeatureExtractor
from modelscope import AutoModelForCausalLM
import safetensors
import random
import torch.nn.functional as F

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


class QwenEmotion:
    def __init__(self, model_dir):
        self.model_dir = model_dir
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_dir,
            torch_dtype="float16",  # "auto"
            device_map="auto"
        )
        self.prompt = "文本情感分类"
        self.cn_key_to_en = {
            "高兴": "happy",
            "愤怒": "angry",
            "悲伤": "sad",
            "恐惧": "afraid",
            "反感": "disgusted",
            "低落": "melancholic",
            "惊讶": "surprised",
            "自然": "calm",
        }
        self.desired_vector_order = ["高兴", "愤怒", "悲伤", "恐惧", "反感", "低落", "惊讶", "自然"]
        self.melancholic_words = {
            "低落",
            "melancholy",
            "melancholic",
            "depression",
            "depressed",
            "gloomy",
        }
        self.max_score = 1.2
        self.min_score = 0.0

    def clamp_score(self, value):
        return max(self.min_score, min(self.max_score, value))

    def convert(self, content):
        emotion_dict = {
            self.cn_key_to_en[cn_key]: self.clamp_score(content.get(cn_key, 0.0))
            for cn_key in self.desired_vector_order
        }

        if all(val <= 0.0 for val in emotion_dict.values()):
            print(">> no emotions detected; using default calm/neutral voice")
            emotion_dict["calm"] = 1.0

        return emotion_dict

    def inference(self, text_input):
        start = time.time()
        messages = [
            {"role": "system", "content": f"{self.prompt}"},
            {"role": "user", "content": f"{text_input}"}
        ]
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        generated_ids = self.model.generate(
            **model_inputs,
            max_new_tokens=32768,
            pad_token_id=self.tokenizer.eos_token_id
        )
        output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist()

        try:
            index = len(output_ids) - output_ids[::-1].index(151668)
        except ValueError:
            index = 0

        content = self.tokenizer.decode(output_ids[index:], skip_special_tokens=True)

        try:
            content = json.loads(content)
        except json.decoder.JSONDecodeError:
            content = {
                m.group(1): float(m.group(2))
                for m in re.finditer(r'([^\s":.,]+?)"?\s*:\s*([\d.]+)', content)
            }

        text_input_lower = text_input.lower()
        if any(word in text_input_lower for word in self.melancholic_words):
            content["悲伤"], content["低落"] = content.get("低落", 0.0), content.get("悲伤", 0.0)

        return self.convert(content)



class IndexTTS2(RefIndexTTS2):
    def __init__(
            self, cfg_path="models/IndexTTS-2/config.yaml", model_dir="models/IndexTTS-2", models_root="models", use_fp16=False, device=None,
            use_cuda_kernel=None, use_deepspeed=False, use_accel=False, use_torch_compile=False
    ):
        if device is not None:
            self.device = device
            self.use_fp16 = False if device == "cpu" else use_fp16
            self.use_cuda_kernel = use_cuda_kernel is not None and use_cuda_kernel and device.startswith("cuda")
        elif torch.cuda.is_available():
            self.device = "cuda:0"
            self.use_fp16 = use_fp16
            self.use_cuda_kernel = use_cuda_kernel is None or use_cuda_kernel
        elif hasattr(torch, "xpu") and torch.xpu.is_available():
            self.device = "xpu"
            self.use_fp16 = use_fp16
            self.use_cuda_kernel = False
        elif hasattr(torch, "mps") and torch.backends.mps.is_available():
            self.device = "mps"
            self.use_fp16 = False
            self.use_cuda_kernel = False
        else:
            self.device = "cpu"
            self.use_fp16 = False
            self.use_cuda_kernel = False
            print(">> Be patient, it may take a while to run in CPU mode.")

        self.models_root = models_root
        self.cfg = OmegaConf.load(cfg_path)
        # models_base_dir = model_dir
        # indextts2_model_dir = os.path.join(models_base_dir, "IndexTTS-2")
        # print(f"indextts2_model_dir:{indextts2_model_dir}")

        self.dtype = torch.float16 if self.use_fp16 else None
        self.stop_mel_token = self.cfg.gpt.stop_mel_token
        self.use_accel = use_accel
        self.use_torch_compile = use_torch_compile

        qwen_emo_path = os.path.join(model_dir, self.cfg.qwen_emo_path)
        self.qwen_emo = QwenEmotion(qwen_emo_path)

        self.gpt = UnifiedVoice(**self.cfg.gpt, use_accel=self.use_accel)
        self.gpt_path = os.path.join(model_dir, self.cfg.gpt_checkpoint)
        load_checkpoint(self.gpt, self.gpt_path)
        self.gpt = self.gpt.to(self.device)
        if self.use_fp16:
            self.gpt.eval().half()
        else:
            self.gpt.eval()
        print(">> GPT weights restored from:", self.gpt_path)

        if use_deepspeed:
            try:
                import deepspeed
            except (ImportError, OSError, CalledProcessError) as e:
                use_deepspeed = False
                print(f">> Failed to load DeepSpeed. Falling back to normal inference. Error: {e}")

        self.gpt.post_init_gpt2_config(use_deepspeed=use_deepspeed, kv_cache=True, half=self.use_fp16)

        if self.use_cuda_kernel:
            try:
                from indextts.s2mel.modules.bigvgan.alias_free_activation.cuda import activation1d
                print(">> Preload custom CUDA kernel for BigVGAN", activation1d.anti_alias_activation_cuda)
            except Exception as e:
                print(">> Failed to load custom CUDA kernel for BigVGAN. Falling back to torch.")
                print(f"{e!r}")
                self.use_cuda_kernel = False
        
                self.use_cuda_kernel = False
        
        self.extract_features = SeamlessM4TFeatureExtractor.from_pretrained(os.path.join(self.models_root, "facebook/w2v-bert-2.0"), local_files_only=True)
        self.semantic_model, self.semantic_mean, self.semantic_std = build_semantic_model(
            os.path.join(model_dir, self.cfg.w2v_stat))
        self.semantic_model = self.semantic_model.to(self.device)
        self.semantic_model.eval()
        self.semantic_mean = self.semantic_mean.to(self.device)
        self.semantic_std = self.semantic_std.to(self.device)

        semantic_codec = build_semantic_codec(self.cfg.semantic_codec)
        semantic_code_ckpt = os.path.join(self.models_root, "amphion/MaskGCT/semantic_codec/model.safetensors")
        safetensors.torch.load_model(semantic_codec, semantic_code_ckpt)
        self.semantic_codec = semantic_codec.to(self.device)
        self.semantic_codec.eval()
        print('>> semantic_codec weights restored from: {}'.format(semantic_code_ckpt))

        s2mel_path = os.path.join(model_dir, self.cfg.s2mel_checkpoint)
        s2mel = MyModel(self.cfg.s2mel, use_gpt_latent=True)
        s2mel, _, _, _ = load_checkpoint2(
            s2mel,
            None,
            s2mel_path,
            load_only_params=True,
            ignore_modules=[],
            is_distributed=False,
        )
        self.s2mel = s2mel.to(self.device)
        self.s2mel.models['cfm'].estimator.setup_caches(max_batch_size=1, max_seq_length=8192)
        
        if self.use_torch_compile:
            print(">> Enabling torch.compile optimization")
            self.s2mel.enable_torch_compile()
            print(">> torch.compile optimization enabled successfully")
        
        self.s2mel.eval()
        print(">> s2mel weights restored from:", s2mel_path)

        campplus_ckpt_path = os.path.join(self.models_root, "funasr/campplus/campplus_cn_common.bin")
        campplus_model = CAMPPlus(feat_dim=80, embedding_size=192)
        campplus_model.load_state_dict(torch.load(campplus_ckpt_path, map_location="cpu"))
        self.campplus_model = campplus_model.to(self.device)
        self.campplus_model.eval()
        print(">> campplus_model weights restored from:", campplus_ckpt_path)

        bigvgan_name = os.path.join(self.models_root, self.cfg.vocoder.name)
        self.bigvgan = bigvgan.BigVGAN.from_pretrained(bigvgan_name, use_cuda_kernel=self.use_cuda_kernel)
        self.bigvgan = self.bigvgan.to(self.device)
        self.bigvgan.remove_weight_norm()
        self.bigvgan.eval()
        print(">> bigvgan weights restored from:", bigvgan_name)

        self.bpe_path = os.path.join(model_dir, self.cfg.dataset["bpe_model"])
        self.normalizer = TextNormalizer()
        self.normalizer.load()
        print(">> TextNormalizer loaded")
        self.tokenizer = TextTokenizer(self.bpe_path, self.normalizer)
        print(">> bpe model loaded from:", self.bpe_path)

        emo_matrix = torch.load(os.path.join(model_dir, self.cfg.emo_matrix))
        self.emo_matrix = emo_matrix.to(self.device)
        self.emo_num = list(self.cfg.emo_num)

        spk_matrix = torch.load(os.path.join(model_dir, self.cfg.spk_matrix))
        self.spk_matrix = spk_matrix.to(self.device)

        self.emo_matrix = torch.split(self.emo_matrix, self.emo_num)
        self.spk_matrix = torch.split(self.spk_matrix, self.emo_num)

        mel_fn_args = {
            "n_fft": self.cfg.s2mel['preprocess_params']['spect_params']['n_fft'],
            "win_size": self.cfg.s2mel['preprocess_params']['spect_params']['win_length'],
            "hop_size": self.cfg.s2mel['preprocess_params']['spect_params']['hop_length'],
            "num_mels": self.cfg.s2mel['preprocess_params']['spect_params']['n_mels'],
            "sampling_rate": self.cfg.s2mel["preprocess_params"]["sr"],
            "fmin": self.cfg.s2mel['preprocess_params']['spect_params'].get('fmin', 0),
            "fmax": None if self.cfg.s2mel['preprocess_params']['spect_params'].get('fmax', "None") == "None" else 8000,
            "center": False
        }
        self.mel_fn = lambda x: mel_spectrogram(x, **mel_fn_args)

        self.cache_spk_cond = None
        self.cache_s2mel_style = None
        self.cache_s2mel_prompt = None
        self.cache_spk_audio_prompt = None
        self.cache_emo_cond = None
        self.cache_emo_audio_prompt = None
        self.cache_mel = None

        self.gr_progress = None
        self.model_version = self.cfg.version if hasattr(self.cfg, "version") else None

    def release_resources(self):
        """显式释放模型资源"""
        print(">> Releasing IndexTTS2 resources...")
        
        # 定义需要释放的组件列表
        components = [
            'qwen_emo', 'gpt', 'extract_features', 'semantic_model', 
            'semantic_codec', 's2mel', 'campplus_model', 'bigvgan',
            'emo_matrix', 'spk_matrix', 'tokenizer', 'normalizer'
        ]
        
        for name in components:
            if hasattr(self, name):
                try:
                    obj = getattr(self, name)
                    # 先尝试移动到CPU，确保显存释放
                    if hasattr(obj, 'cpu'):
                        try:
                            obj.cpu()
                        except:
                            pass
                    elif hasattr(obj, 'to'):
                        try:
                            obj.to('cpu')
                        except:
                            pass
                    
                    # 删除引用
                    delattr(self, name)
                    del obj
                except Exception as e:
                    print(f">> Error deleting {name}: {e}")
        
        # 清理缓存
        self.cache_spk_cond = None
        self.cache_s2mel_style = None
        self.cache_s2mel_prompt = None
        self.cache_spk_audio_prompt = None
        self.cache_emo_cond = None
        self.cache_emo_audio_prompt = None
        self.cache_mel = None
        
        # 强制显存清理
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect() # 额外的清理
            
        import gc
        gc.collect()
        print(">> IndexTTS2 resources released.")
