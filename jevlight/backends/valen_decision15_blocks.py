"""Valen-Decision-1.5 block ids and block-structured full attention.

The released ``bbox_blocks`` mask applies to full-attention layers only: the
state prefix is bidirectional and never sees the question region, the shared
chat-turn glue sees the prefix and itself, and decision questions share one
bidirectional block that also sees the prefix and the glue. Linear-attention
layers stay causal. Block ids follow the frozen compiler: prefix -1, glue 0,
decision questions 1.
"""

PREFIX, COMMON, DECISION = -1, 0, 1
# The frozen compiler closes each state with these two turns: schemas, then readouts.
GLUE = ('<|im_start|>user\n', '<|im_end|>\n<|im_start|>assistant\n')


def glue_tokens(tokenizer):
    glue = [list(tokenizer.encode(text, add_special_tokens=False)) for text in GLUE]
    opener = glue[0][0]
    if not glue[0] or glue[0].count(opener) != 1 or glue[1].count(opener) != 1:
        raise ValueError('Tokenizer does not keep one chat-turn opener per glue turn')
    return glue


def prompt_segments(ids, glue):
    """Block id per token of one complete prompt, or None without the closing turns.

    State and question text cannot contain chat control tokens (the compiler
    rejects them), so the last two turn openers are the block boundaries.
    """
    ids = list(ids)
    opener = glue[0][0]
    turns = [index for index, token in enumerate(ids) if token == opener]
    if len(turns) < 2:
        return None
    user, assistant = turns[-2:]
    closing = assistant - glue[1].index(opener)
    if (user < 1 or ids[user:user + len(glue[0])] != glue[0] or closing < user + len(glue[0])
            or ids[closing:closing + len(glue[1])] != glue[1]):
        return None
    segments = [PREFIX] * user + [DECISION] * (len(ids) - user)
    for begin, length in ((user, len(glue[0])), (closing, len(glue[1]))):
        segments[begin:begin + length] = [COMMON] * length
    return segments


def compiled_segments(state):
    """The frozen compiler's block ids of one shared row under ``bbox_blocks``."""
    branches = [question.branches[0] for question in state.questions]
    first = branches[0]
    if any(branch.segments is not first.segments or branch.bbox_segments for branch in branches):
        raise ValueError('Decision questions must share one text-only block row')
    return [DECISION if value > COMMON else value for value in (int(v) for v in first.segments)]


def block_attention(query, key, value, segments, scale):
    """query [L, H, D], key/value [L, KV, D] and block ids [L] of one prompt; returns [L, H, D]."""
    import torch
    import torch.nn.functional as F
    groups = query.shape[1] // key.shape[1]
    q = query.transpose(0, 1)
    k = key.transpose(0, 1).repeat_interleave(groups, 0)
    v = value.transpose(0, 1).repeat_interleave(groups, 0)
    output = torch.empty_like(q)
    prefix = segments == PREFIX
    shared = prefix | (segments == COMMON)
    for block in segments.unique():
        rows = segments == block
        keys = prefix if block == PREFIX else shared | rows
        output[:, rows] = F.scaled_dot_product_attention(q[:, rows], k[:, keys], v[:, keys], scale=scale)
    return output.transpose(0, 1)
