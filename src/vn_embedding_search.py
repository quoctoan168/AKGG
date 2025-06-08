# -*- coding: utf-8 -*-
import os
import pickle
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# Set environment variable to avoid OpenMP conflict
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

# Print NumPy version for debugging
print(f"NumPy: {np.__version__}")

# ---------- CẤU HÌNH ----------
VECTOR_DIM = 768  # Adjust based on model
MODEL_NAME = 'keepitreal/vietnamese-sbert'
INDEX_PATH = "faiss_index.index"
PHRASE_MAP_PATH = "phrase_map.pkl"

# ---------- KHỞI TẠO MODEL ----------
try:
    model = SentenceTransformer(MODEL_NAME)
    print(f"Actual model embedding dimension: {model.get_sentence_embedding_dimension()}")
except Exception as e:
    raise Exception(f"Failed to load model {MODEL_NAME}: {str(e)}")

# ---------- CÁC HÀM CHÍNH ----------

def embed_phrases(phrases):
    """Chuyển danh sách cụm từ thành vector"""
    return model.encode(phrases).astype('float32')

def build_index(phrases, save=True):
    """Xây FAISS index từ danh sách cụm từ"""
    vectors = embed_phrases(phrases)
    index = faiss.IndexFlatL2(VECTOR_DIM)
    index.add(vectors)
    phrase_map = {i: p for i, p in enumerate(phrases)}
    
    if save:
        save_index(index, phrase_map)

    return index, phrase_map

def save_index(index, phrase_map):
    """Lưu FAISS index và bản đồ cụm từ"""
    faiss.write_index(index, INDEX_PATH)
    with open(PHRASE_MAP_PATH, "wb") as f:
        pickle.dump(phrase_map, f)

def load_index():
    """Tải lại FAISS index và phrase map từ ổ đĩa"""
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError("FAISS index chưa được tạo.")
    if not os.path.exists(PHRASE_MAP_PATH):
        raise FileNotFoundError("Phrase map chưa được tạo.")
    index = faiss.read_index(INDEX_PATH)
    with open(PHRASE_MAP_PATH, "rb") as f:
        phrase_map = pickle.load(f)
    return index, phrase_map

def search_phrase(query, top_k=5):
    """Tìm cụm từ gần nhất với query"""
    query_vec = model.encode([query]).astype('float32')
    index, phrase_map = load_index()
    D, I = index.search(query_vec, top_k)
    return [phrase_map[i] for i in I[0]]