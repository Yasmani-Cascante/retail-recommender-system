# tests/performance/benchmark_category.py
import time
# from src.recommenders.tfidf_recommender import TFIDFRecommender

# Initialize recommender and build category index
# tfidf_recommender = TFIDFRecommender()
# category_index = tfidf_recommender.category_index

def benchmark_category_lookup():
    # O(n) approach
    start = time.time()
    products = [p for p in all_products  if p["category"] == "LENCERIA"]
    # products = [p f ,or p in tfidf_recommender.product_data if p["category"] == "LENCERIA"]
    time_on = (time.time() - start) * 1000
    
    # O(1) approach
    start = time.time()
    products = category_index.get("LENCERIA", [])
    time_o1 = (time.time() - start) * 1000
    
    print(f"O(n): {time_on:.2f}ms")
    print(f"O(1): {time_o1:.2f}ms")
    print(f"Speedup: {time_on / time_o1:.1f}x")

# Expected output:
# O(n): 8.45ms
# O(1): 0.42ms
# Speedup: 20.1x