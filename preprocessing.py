from collections import defaultdict

# ------------------------------------------------------------
# Tokenization
# ------------------------------------------------------------
# import dedicated tokenizer or use simple one
import spacy
nlp = spacy.load("en_core_web_sm")
def tokenize_transcript_entries(transcript_data, max_seq_len=256, vocab_size=10000):
    # Build vocabulary from transcript
    word_freq = defaultdict(int)
    
    for entry in transcript_data:
        doc = nlp(entry['text'].lower())
        for token in doc:
            if not token.is_punct and not token.is_space:
                word_freq[token.text] += 1
    
    # Sort words by frequency and take top vocab_size
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    vocab_words = [word for word, freq in sorted_words[:vocab_size - 2]]  # Reserve 0 for PAD, 1 for UNK
    
    # Create word to index mapping
    word2idx = {word: idx + 2 for idx, word in enumerate(vocab_words)}
    word2idx['<PAD>'] = 0
    word2idx['<UNK>'] = 1
    
    # Tokenize entries
    sequences = []
    
    for entry in transcript_data:
        doc = nlp(entry['text'].lower())
        token_indices = []
        
        for token in doc:
            if not token.is_punct and not token.is_space:
                idx = word2idx.get(token.text, word2idx['<UNK>'])
                token_indices.append(idx)
        
        # Truncate or pad to max_seq_len
        if len(token_indices) > max_seq_len:
            token_indices = token_indices[:max_seq_len]
        else:
            token_indices += [word2idx['<PAD>']] * (max_seq_len - len(token_indices))
        
        sequences.append(token_indices)
    
    return sequences