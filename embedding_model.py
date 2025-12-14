# -------------------------------------------------------------
# Neural Network Embedding Model
# -------------------------------------------------------------
import numpy as np
import torch
import torch.nn as nn
from preprocessing import tokenize_transcript_entries

class SimpleEmbeddingModel(nn.Module):
    """
    CNN + Attention embedding model for learning word representations
    Architecture: Embedding → CNN (local patterns) → Attention (global context)
    Trained on the transcript using self-supervised learning
    """
    
    def __init__(self, num_tokens, emb_size, max_seq_len, cnn_kernel_sizes=[3, 5, 7], cnn_num_filters=64):
        super().__init__()
        
        # Embedding layers
        self.embedding = nn.Embedding(num_tokens, emb_size)
        self.pos_encoding = nn.Embedding(max_seq_len, emb_size)
        
        # CNN layers for local feature extraction
        # Multiple kernel sizes to capture different n-gram patterns
        self.cnn_kernel_sizes = cnn_kernel_sizes
        self.cnn_num_filters = cnn_num_filters
        
        self.convs = nn.ModuleList([
            nn.Conv1d(
                in_channels=emb_size,
                out_channels=cnn_num_filters,
                kernel_size=k,
                padding=k//2  # Same padding to preserve sequence length
            )
            for k in cnn_kernel_sizes
        ])
        
        # Batch normalization for each conv layer
        self.batch_norms = nn.ModuleList([
            nn.BatchNorm1d(cnn_num_filters)
            for _ in cnn_kernel_sizes
        ])
        
        # Project concatenated CNN features back to emb_size
        cnn_output_size = cnn_num_filters * len(cnn_kernel_sizes)
        self.cnn_projection = nn.Linear(cnn_output_size, emb_size)
        
        # Learned Q/K/V projections (operate on CNN-enhanced features)
        self.query = nn.Linear(emb_size, emb_size)
        self.key = nn.Linear(emb_size, emb_size)
        self.value = nn.Linear(emb_size, emb_size)
        
        # Reconstruction head (for self-supervised learning)
        self.reconstruct = nn.Linear(emb_size, num_tokens)
        
        self.emb_size = emb_size
        self.max_seq_len = max_seq_len
    
    def apply_cnn(self, embeddings):
        """
        Apply CNN to extract local n-gram features
        
        Args:
            embeddings: (batch, seq_len, emb_size)
        
        Returns:
            cnn_features: (batch, seq_len, emb_size)
        """
        # Conv1d expects (batch, channels, seq_len)
        x = embeddings.transpose(1, 2)  # (batch, emb_size, seq_len)
        
        # Apply each CNN with different kernel sizes
        conv_outputs = []
        for conv, bn in zip(self.convs, self.batch_norms):
            # Convolution
            conv_out = conv(x)  # (batch, num_filters, seq_len)
            
            # Batch normalization
            conv_out = bn(conv_out)
            
            # ReLU activation
            conv_out = torch.relu(conv_out)
            
            conv_outputs.append(conv_out)
        
        # Concatenate features from different kernel sizes
        # (batch, num_filters * num_kernels, seq_len)
        concat_features = torch.cat(conv_outputs, dim=1)
        
        # Transpose back to (batch, seq_len, num_filters * num_kernels)
        concat_features = concat_features.transpose(1, 2)
        
        # Project back to emb_size
        cnn_features = self.cnn_projection(concat_features)
        
        # Residual connection: add original embeddings
        cnn_features = cnn_features + embeddings
        
        return cnn_features
    
    def forward(self, x, return_embeddings=False, return_cnn_features=False):
        """
        Forward pass: Embedding → CNN → Attention → Reconstruction
        
        Args:
            x: (batch, seq_len) - Input token indices
            return_embeddings: If True, return raw embeddings
            return_cnn_features: If True, return CNN-enhanced features
        
        Returns:
            output or embeddings or cnn_features
        """
        batch_size, seq_len = x.shape
        
        # Step 1: Embedding + positional encoding
        positions = torch.arange(seq_len, device=x.device).unsqueeze(0).expand(batch_size, -1)
        embeddings = self.embedding(x) + self.pos_encoding(positions)
        
        if return_embeddings:
            return embeddings
        
        # Step 2: Apply CNN to extract local features
        cnn_features = self.apply_cnn(embeddings)
        
        if return_cnn_features:
            return cnn_features
        
        # Step 3: Compute Q, K, V from CNN-enhanced features
        Q = self.query(cnn_features)
        K = self.key(cnn_features)
        V = self.value(cnn_features)
        
        # Step 4: Scaled dot product attention
        attn_weights = torch.einsum('bte,bse->bts', Q, K)
        attn_weights = attn_weights / (self.emb_size ** 0.5)
        
        pad_mask = (x == 0).unsqueeze(1)
        attn_weights = attn_weights.masked_fill(pad_mask, float('-inf'))
        
        attn_weights = torch.softmax(attn_weights, dim=2)
        
        # Step 5: Weighted sum
        attended = torch.einsum('bts,bse->bte', attn_weights, V)
        
        # Step 6: Reconstruct tokens (self-supervised objective)
        output = self.reconstruct(attended)
        
        return output
    
    def get_embeddings(self, x, use_cnn=True):
        """
        Get embeddings for tokens
        
        Args:
            x: (batch, seq_len) - Input tokens
            use_cnn: If True, return CNN-enhanced features; else raw embeddings
        
        Returns:
            embeddings: (batch, seq_len, emb_size) numpy array
        """
        with torch.no_grad():
            if use_cnn:
                embeddings = self.forward(x, return_cnn_features=True)
            else:
                embeddings = self.forward(x, return_embeddings=True)
        return embeddings.cpu().numpy()
    
# -------------------------------------------------------------
# NN Training
# -------------------------------------------------------------
def train_embedding_model(transcript_data, emb_size=128, epochs=10, cnn_kernel_sizes=[3, 5, 7]):
    
    # Tokenize all entries
    vocab_size = 10000
    max_seq_len = 256
    sequences = tokenize_transcript_entries(transcript_data, max_seq_len, vocab_size)
    
    # Convert to tensors
    X = torch.tensor(sequences, dtype=torch.long)
    
    print(f"Dataset: {len(X)} sequences, vocab_size={vocab_size}, seq_len={max_seq_len}")
    print(f"CNN kernel sizes: {cnn_kernel_sizes} (captures {min(cnn_kernel_sizes)}-{max(cnn_kernel_sizes)} gram features)")
    
    # Initialize model with CNN
    model = SimpleEmbeddingModel(
        num_tokens=vocab_size,
        emb_size=emb_size,
        max_seq_len=max_seq_len,
        cnn_kernel_sizes=cnn_kernel_sizes,
        cnn_num_filters=16
    )
    
    # Training setup
    optimizer = torch.optim.Adam(model.parameters(), lr=25e-4)
    # Ignore padding index (0) in loss calculation
    criterion = nn.CrossEntropyLoss(ignore_index=0)
    
    # Shuffle data before splitting to ensure validation set is representative
    indices = torch.randperm(len(X))
    X_shuffled = X[indices]
    
    # Simple train-val split
    n_train = int(0.85 * len(X))
    X_train = X_shuffled[:n_train]
    X_val = X_shuffled[n_train:]
    
    batch_size = 32
    
    print(f"Training: {len(X_train)} samples, Validation: {len(X_val)} samples")
    print(f"Training for {epochs} epochs...")
    
    for epoch in range(epochs):
        # Training
        model.train()
        train_loss = 0.0
        
        # Mini-batch training
        for i in range(0, len(X_train), batch_size):
            batch = X_train[i:i+batch_size]
            
            optimizer.zero_grad()
            
            # Forward pass (includes CNN → Attention → Reconstruction)
            output = model(batch)  # (batch, seq_len, vocab_size)
            
            # Reshape for loss calculation
            output_flat = output.view(-1, vocab_size)
            target_flat = batch.view(-1)
            
            loss = criterion(output_flat, target_flat)
            
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
        
        # Validation
        model.eval()
        val_loss = 0.0
        
        with torch.no_grad():
            for i in range(0, len(X_val), batch_size):
                batch = X_val[i:i+batch_size]
                output = model(batch)
                
                output_flat = output.view(-1, vocab_size)
                target_flat = batch.view(-1)
                
                loss = criterion(output_flat, target_flat)
                val_loss += loss.item()
        
        train_loss /= (len(X_train) / batch_size)
        val_loss /= (len(X_val) / batch_size)
        
        print(f"Epoch {epoch+1}/{epochs}: train_loss={train_loss:.4f}, val_loss={val_loss:.4f}")
    
    print("Training complete! CNN has learned local n-gram patterns.")
    print("=" * 60)
    
    return model

# -------------------------------------------------------------
# Extract Embeddings from Trained Model
# -------------------------------------------------------------
def extract_sentence_embeddings(transcript_data, model, use_cnn=True):
    """
    Extract embeddings for each sentence using the trained CNN+Attention model
    
    Args:
        transcript_data: List of transcript entry dicts
        model: Trained SimpleEmbeddingModel (with CNN)
        use_cnn: If True, use CNN-enhanced features; else raw embeddings
    
    Returns:
        list: List of sentence embedding matrices
    """    
    print(f"Extracting {'CNN-enhanced' if use_cnn else 'raw'} sentence embeddings from trained model...")
    
    # Tokenize
    vocab_size = 10000
    max_seq_len = 128
    sequences = tokenize_transcript_entries(transcript_data, max_seq_len, vocab_size)
    X = torch.tensor(sequences, dtype=torch.long)
    
    # Get embeddings in batches
    model.eval()
    all_embeddings = []
    batch_size = 32
    
    with torch.no_grad():
        for i in range(0, len(X), batch_size):
            batch = X[i:i+batch_size]
            embeddings = model.get_embeddings(batch, use_cnn=use_cnn)  # (batch, seq_len, emb_dim)
            
            # Store each sentence's embedding matrix separately
            for emb in embeddings:
                # Remove padding (zeros)
                non_zero_mask = np.any(emb != 0, axis=1)
                cleaned_emb = emb[non_zero_mask]
                
                if len(cleaned_emb) == 0:
                    cleaned_emb = np.zeros((1, emb.shape[1]))
                
                all_embeddings.append(cleaned_emb)
    
    print(f"Extracted {len(all_embeddings)} sentence embeddings (CNN-enhanced features)")
    
    return all_embeddings