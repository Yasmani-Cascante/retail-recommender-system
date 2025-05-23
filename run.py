import uvicorn

if __name__ == "__main__":
    # uvicorn.run("src.api.main:app", host="localhost", port=8000, reload=True)
    uvicorn.run("src.api.main_tfidf_shopify_with_metrics:app", host="localhost", port=8000, reload=True)