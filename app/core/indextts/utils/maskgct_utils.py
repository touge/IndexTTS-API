import os
import torch
from transformers import Wav2Vec2BertModel

from indextts.utils.maskgct.models.codec.kmeans.repcodec_model import RepCodec


def build_semantic_model(stat_path, model_base_dir='models'):
    """
    构建语义模型
    
    Args:
        stat_path: 统计文件路径 (wav2vec2bert_stats.pt)
        model_base_dir: 模型基础目录,默认为 'models'
    
    Returns:
        semantic_model, semantic_mean, semantic_std
    """
    semantic_model = Wav2Vec2BertModel.from_pretrained(
        os.path.join(model_base_dir, "facebook/w2v-bert-2.0")
    )
    semantic_model.eval()
    stat_mean_var = torch.load(stat_path)
    semantic_mean = stat_mean_var["mean"]
    semantic_std = torch.sqrt(stat_mean_var["var"])
    return semantic_model, semantic_mean, semantic_std


def build_semantic_codec(cfg):
    """
    构建语义编解码器
    
    Args:
        cfg: 编解码器配置
    
    Returns:
        semantic_codec
    """
    semantic_codec = RepCodec(cfg=cfg)
    semantic_codec.eval()
    return semantic_codec