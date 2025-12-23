import logging
from indextts.infer import IndexTTS as RefIndexTTS

logger = logging.getLogger(__name__)

class IndexTTS(RefIndexTTS):
    """
    IndexTTS V1.5 包装类
    继承自 indextts.infer.IndexTTS，适配 IndexTTS2GUI 的调用接口
    """
    def __init__(self, cfg_path="checkpoints/config.yaml", model_dir="checkpoints", use_fp16=True, device=None, use_cuda_kernel=None):
        super().__init__(cfg_path, model_dir, use_fp16, device, use_cuda_kernel)
        self.model_version = 1.5

    def infer_generator(self, text, spk_audio_prompt, output_path, verbose=False, **kwargs):
        """
        适配 TTSGenerator 的调用接口
        IndexTTS V1.5 原生不支持 generator 模式，这里做一个简单的包装
        """
        # 参数映射: TTSGenerator 使用 spk_audio_prompt, V1.5 使用 audio_prompt
        audio_prompt = spk_audio_prompt
        
        # 移除 V1.5 不支持或不需要的参数，避免传入 infer 导致错误或警告
        # 也可以保留，因为 base.infer 会接收 **generation_kwargs
        
        # 调用基类的 infer 方法
        # 注意: 这里可以选择调用 infer 或 infer_fast
        # 鉴于 infer_fast 对长文本优化更好，且在基类中存在，优先尝试使用 infer_fast?
        # 但为了稳健性，先使用标准 infer
        
        try:
            # 过滤掉不需要的参数 (如 emotion 相关)
            # base.infer 接受 **generation_kwargs, 所以多余参数会传给 GPT inference
            # 最好清理一下明确不支持的参数
            valid_kwargs = {k: v for k, v in kwargs.items() if k not in [
                'emotion_mode', 'emo_audio_prompt', 'emo_alpha', 'emo_vector', 'emo_text', 
                'use_emo_text', 'use_random', 'use_chunking'
            ]}
            
            # 暂时使用 infer 方法
            logger.info("Using IndexTTS V1.5 infer...")
            ret = self.infer(
                text=text,
                audio_prompt=audio_prompt,
                output_path=output_path,
                verbose=verbose,
                **valid_kwargs
            )
            
            # infer 返回的是 output_path (如果提供了) 或 (sr, wav)
            # TTSGenerator 期望的是 generator yield
            yield ret
            
        except Exception as e:
            logger.error(f"IndexTTS V1.5 inference failed: {e}")
            raise e

    def release_resources(self):
        """显式释放模型资源"""
        import torch
        import gc
        logger.info("Releasing IndexTTS V1.5 resources...")
        
        components = ['gpt', 'bigvgan', 'tokenizer', 'normalizer']
        for name in components:
            if hasattr(self, name):
                try:
                    obj = getattr(self, name)
                    if hasattr(obj, 'cpu'):
                        obj.cpu()
                    elif hasattr(obj, 'to'):
                        try:
                            obj.to('cpu')
                        except:
                            pass
                    delattr(self, name)
                    del obj
                except Exception as e:
                    logger.error(f"Error deleting {name}: {e}")
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        gc.collect()
        logger.info("IndexTTS V1.5 resources released.")
