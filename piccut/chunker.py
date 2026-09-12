"""Smart word chunking for vertical short captions.
Groups word-level timestamps into target captions of N words while respecting
natural speech pauses and punctuation boundaries.
"""

from typing import List, Dict, Any

def chunk_words_to_captions(
    words: List[Dict[str, Any]],
    target_words_per_caption: int = 3,
    max_pause_sec: float = 0.5,
    bridge_micro_gaps: bool = True
) -> List[Dict[str, Any]]:
    """Group a list of word timestamps into caption cues for vertical video.
    
    Args:
        words: List of dicts with 'word', 'start', 'end', optional 'probability'.
        target_words_per_caption: Target number of words per caption cue (e.g. 1, 2, 3, 4, 5).
        max_pause_sec: Maximum pause between words before splitting into a new cue.
        bridge_micro_gaps: Whether to extend word end times to the next word start if gap is tiny.
        
    Returns:
        List of caption dictionaries:
        [
            {
                "id": int,
                "text": str,
                "start": float,
                "end": float,
                "words": [
                    {"word": str, "start": float, "end": float, "probability": float},
                    ...
                ]
            },
            ...
        ]
    """
    if not words:
        return []

    target_words = max(1, target_words_per_caption)
    captions: List[Dict[str, Any]] = []
    
    current_words: List[Dict[str, Any]] = []
    
    for i, w in enumerate(words):
        word_text = str(w.get("word", "")).strip()
        if not word_text:
            continue
            
        w_start = float(w.get("start", 0.0))
        w_end = float(w.get("end", w_start + 0.2))
        prob = float(w.get("probability", 1.0))
        
        current_word_clean = {
            "word": word_text,
            "start": round(w_start, 3),
            "end": round(w_end, 3),
            "probability": round(prob, 3)
        }
        
        if not current_words:
            current_words.append(current_word_clean)
            continue
            
        last_word = current_words[-1]
        pause = w_start - last_word["end"]
        
        # Check if previous word had terminal punctuation
        last_text = last_word["word"]
        has_terminal_punct = last_text.endswith((".", "!", "?"))
        
        # Split condition: reached target word count, or long pause, or terminal punctuation
        should_split = (
            len(current_words) >= target_words
            or pause >= max_pause_sec
            or has_terminal_punct
        )
        
        if should_split:
            # Finalize current caption
            captions.append(_build_caption(len(captions), current_words, bridge_micro_gaps))
            current_words = [current_word_clean]
        else:
            current_words.append(current_word_clean)
            
    if current_words:
        captions.append(_build_caption(len(captions), current_words, bridge_micro_gaps))
        
    return captions

def _build_caption(caption_id: int, words: List[Dict[str, Any]], bridge_micro_gaps: bool) -> Dict[str, Any]:
    """Helper to assemble a single caption object from a list of words."""
    if not words:
        return {"id": caption_id, "text": "", "start": 0.0, "end": 0.0, "words": []}

    processed_words = []
    for i, w in enumerate(words):
        w_copy = dict(w)
        if bridge_micro_gaps and i < len(words) - 1:
            next_start = words[i + 1]["start"]
            gap = next_start - w_copy["end"]
            # Bridge gaps up to 0.25s to avoid visual subtitle flickering
            if 0 < gap <= 0.25:
                w_copy["end"] = round(next_start, 3)
        processed_words.append(w_copy)

    caption_start = processed_words[0]["start"]
    caption_end = processed_words[-1]["end"]
    caption_text = " ".join(w["word"] for w in processed_words)

    return {
        "id": caption_id,
        "text": caption_text,
        "start": caption_start,
        "end": caption_end,
        "words": processed_words
    }
