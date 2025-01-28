from setuptools import setup, find_packages

setup(
    name="retail-recommender",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "sentence-transformers>=2.2.0",
        "scikit-learn>=0.24.2",
        "numpy>=1.21.0",
        "pandas>=1.3.0",
        "python-dotenv>=0.19.0",
        "requests>=2.26.0"
    ],
)