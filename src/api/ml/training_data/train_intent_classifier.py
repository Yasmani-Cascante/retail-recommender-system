"""
Intent Classifier Training Script
==================================

Entrena un modelo sklearn (TF-IDF + Logistic Regression) para
clasificación de intents INFORMATIONAL vs TRANSACTIONAL.

Autor: AI Assistant
Fecha: 02 Enero 2026
Dataset: vertex-ai-dataset.csv (4,944 queries)
"""

import pandas as pd
import numpy as np
import joblib
import json
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import time

# Configuración
DATASET_PATH = "vertex-ai-dataset.csv"
MODEL_DIR = Path("models/intent_classifier")
RANDOM_STATE = 42

# Asegurar que el directorio existe
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def load_dataset(path: str) -> pd.DataFrame:
    """
    Carga el dataset de entrenamiento
    
    Formato esperado:
    - text: Query del usuario
    - label: INFORMATIONAL | TRANSACTIONAL
    """
    print("📊 Cargando dataset...")
    df = pd.read_csv(path)
    
    print(f"✅ Dataset cargado: {len(df)} queries")
    print(f"   Columnas: {list(df.columns)}")
    
    # Validar formato
    assert 'text' in df.columns, "Falta columna 'text'"
    assert 'label' in df.columns, "Falta columna 'label'"
    
    # Estadísticas
    print(f"\n📈 Distribución de labels:")
    label_dist = df['label'].value_counts()
    for label, count in label_dist.items():
        pct = (count / len(df)) * 100
        print(f"   {label}: {count} ({pct:.1f}%)")
    
    return df


def preprocess_text(text: str) -> str:
    """
    Preprocesamiento básico del texto
    
    Para español, mantenemos simple:
    - Lowercase
    - Preservar acentos (importantes en español)
    - Preservar signos de interrogación
    """
    if pd.isna(text):
        return ""
    
    # Solo lowercase, nada más
    # sklearn's TfidfVectorizer manejará el resto
    return str(text).lower().strip()


def train_model(df: pd.DataFrame):
    """
    Entrena modelo TF-IDF + Logistic Regression
    
    Pipeline:
    1. TF-IDF vectorization (max 5000 features)
    2. Logistic Regression (max_iter=1000)
    3. Cross-validation (5 folds)
    4. Train/test split (80/20)
    """
    
    print("\n" + "=" * 80)
    print("🤖 ENTRENANDO MODELO")
    print("=" * 80)
    
    # Preprocesar textos
    print("\n📝 Preprocesando textos...")
    df['text_clean'] = df['text'].apply(preprocess_text)
    
    # Preparar X, y
    X = df['text_clean']
    y = df['label']
    
    print(f"✅ {len(X)} textos procesados")
    
    # Split train/test
    print("\n✂️ Dividiendo dataset (80% train, 20% test)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, 
        test_size=0.2, 
        random_state=RANDOM_STATE,
        stratify=y  # Mantener distribución de labels
    )
    
    print(f"✅ Train: {len(X_train)} | Test: {len(X_test)}")
    
    # TF-IDF Vectorizer
    print("\n🔤 Entrenando TF-IDF Vectorizer...")
    vectorizer = TfidfVectorizer(
        max_features=5000,  # Top 5000 palabras más importantes
        ngram_range=(1, 2),  # Unigrams y bigrams
        min_df=2,  # Palabra debe aparecer al menos 2 veces
        max_df=0.8,  # Palabra no puede aparecer en más del 80% docs
        strip_accents=None,  # NO remover acentos (importante en español)
        lowercase=True,
        token_pattern=r'\b\w+\b'  # Palabras completas
    )
    
    start_time = time.time()
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)
    vectorizer_time = time.time() - start_time
    
    print(f"✅ Vocabulario: {len(vectorizer.vocabulary_)} palabras")
    print(f"   Tiempo: {vectorizer_time:.2f}s")
    print(f"   Shape: {X_train_vec.shape}")
    
    # Top palabras por clase (para debugging)
    feature_names = vectorizer.get_feature_names_out()
    print(f"\n🔍 Muestra de features (primeras 20):")
    print(f"   {list(feature_names[:20])}")
    
    # Logistic Regression
    print("\n🎯 Entrenando Logistic Regression...")
    model = LogisticRegression(
        max_iter=1000,
        random_state=RANDOM_STATE,
        C=1.0,  # Regularización (default)
        solver='lbfgs',
        class_weight='balanced'  # Balance clases automáticamente
    )
    
    start_time = time.time()
    model.fit(X_train_vec, y_train)
    training_time = time.time() - start_time
    
    print(f"✅ Modelo entrenado en {training_time:.2f}s")
    print(f"   Clases: {model.classes_}")
    print(f"   Coeficientes shape: {model.coef_.shape}")
    
    # Cross-validation
    print("\n🔁 Cross-validation (5 folds)...")
    cv_scores = cross_val_score(
        model, X_train_vec, y_train, 
        cv=5, 
        scoring='accuracy'
    )
    
    print(f"✅ CV Accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")
    print(f"   Fold scores: {cv_scores}")
    
    # Evaluación en test set
    print("\n📊 Evaluación en Test Set...")
    y_pred = model.predict(X_test_vec)
    y_pred_proba = model.predict_proba(X_test_vec)
    
    test_accuracy = accuracy_score(y_test, y_pred)
    print(f"✅ Test Accuracy: {test_accuracy:.4f} ({test_accuracy*100:.2f}%)")
    
    # Classification report
    print("\n📈 Classification Report:")
    print(classification_report(y_test, y_pred, digits=4))
    
    # Confusion matrix
    print("🔢 Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(cm)
    
    classes = model.classes_
    print(f"\n   Interpretación:")
    print(f"   TN (True {classes[0]}): {cm[0][0]}")
    print(f"   FP (False {classes[1]}): {cm[0][1]}")
    print(f"   FN (False {classes[0]}): {cm[1][0]}")
    print(f"   TP (True {classes[1]}): {cm[1][1]}")
    
    # Análisis de confidence
    print("\n📉 Análisis de Confianza (Probabilidades):")
    confidences = np.max(y_pred_proba, axis=1)
    print(f"   Mean confidence: {confidences.mean():.4f}")
    print(f"   Median confidence: {np.median(confidences):.4f}")
    print(f"   Min confidence: {confidences.min():.4f}")
    print(f"   Max confidence: {confidences.max():.4f}")
    
    # Queries con baja confidence (potencialmente difíciles)
    low_conf_threshold = 0.7
    low_conf_indices = np.where(confidences < low_conf_threshold)[0]
    
    if len(low_conf_indices) > 0:
        print(f"\n⚠️ {len(low_conf_indices)} queries con confidence < {low_conf_threshold}:")
        for idx in low_conf_indices[:5]:  # Mostrar primeras 5
            test_idx = X_test.index[idx]
            query = df.loc[test_idx, 'text']
            true_label = y_test.iloc[idx]
            pred_label = y_pred[idx]
            conf = confidences[idx]
            
            correct = "✅" if true_label == pred_label else "❌"
            print(f"   {correct} {query[:50]}...")
            print(f"      True: {true_label} | Pred: {pred_label} | Conf: {conf:.3f}")
    
    # Top palabras predictivas
    print("\n🏆 Top 10 Palabras Más Predictivas por Clase:")
    for i, class_name in enumerate(classes):
        # Coeficientes para esta clase
        coef = model.coef_[i] if len(classes) > 2 else model.coef_[0]
        
        # Top palabras positivas (indican esta clase)
        top_indices = np.argsort(coef)[-10:][::-1]
        top_words = [feature_names[idx] for idx in top_indices]
        top_coefs = [coef[idx] for idx in top_indices]
        
        print(f"\n   {class_name}:")
        for word, coef_val in zip(top_words, top_coefs):
            print(f"      {word}: {coef_val:.4f}")
    
    return vectorizer, model, {
        'test_accuracy': test_accuracy,
        'cv_mean': cv_scores.mean(),
        'cv_std': cv_scores.std(),
        'training_time': training_time,
        'vectorizer_time': vectorizer_time,
        'vocab_size': len(vectorizer.vocabulary_),
        'train_size': len(X_train),
        'test_size': len(X_test)
    }


def save_model(vectorizer, model, metrics: dict):
    """
    Guarda modelo, vectorizer y metadata
    """
    print("\n" + "=" * 80)
    print("💾 GUARDANDO MODELO")
    print("=" * 80)
    
    # Guardar vectorizer
    vectorizer_path = MODEL_DIR / "vectorizer.pkl"
    joblib.dump(vectorizer, vectorizer_path)
    print(f"✅ Vectorizer guardado: {vectorizer_path}")
    
    # Guardar model
    model_path = MODEL_DIR / "model.pkl"
    joblib.dump(model, model_path)
    print(f"✅ Model guardado: {model_path}")
    
    # Guardar metadata
    metadata = {
        'model_type': 'TfidfVectorizer + LogisticRegression',
        'training_date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'dataset': DATASET_PATH,
        'metrics': metrics,
        'classes': model.classes_.tolist(),
        'hyperparameters': {
            'tfidf': {
                'max_features': 5000,
                'ngram_range': (1, 2),
                'min_df': 2,
                'max_df': 0.8
            },
            'logistic_regression': {
                'max_iter': 1000,
                'C': 1.0,
                'solver': 'lbfgs',
                'class_weight': 'balanced'
            }
        }
    }
    
    metadata_path = MODEL_DIR / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Metadata guardada: {metadata_path}")
    
    # Calcular tamaño total
    total_size = (
        vectorizer_path.stat().st_size + 
        model_path.stat().st_size + 
        metadata_path.stat().st_size
    )
    
    print(f"\n📦 Tamaño total del modelo: {total_size / 1024 / 1024:.2f} MB")
    print(f"   Vectorizer: {vectorizer_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"   Model: {model_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"   Metadata: {metadata_path.stat().st_size / 1024:.2f} KB")


def test_model_inference(vectorizer, model):
    """
    Test rápido de inferencia con queries de ejemplo
    """
    print("\n" + "=" * 80)
    print("🧪 PROBANDO INFERENCIA")
    print("=" * 80)
    
    test_queries = [
        # INFORMATIONAL esperadas
        "¿Cuál es la política de devolución?",
        "cuanto cuesta el envio",
        "aceptan PayPal",
        "¿Se puede lavar en lavadora?",
        
        # TRANSACTIONAL esperadas
        "busco vestido largo para boda",
        "necesito bralette en talla M",
        "quiero comprar el vestido Emma",
        "ver detalles del clutch Leonor",
        
        # Casos ambiguos
        "vestido de novia",
        "información sobre lencería"
    ]
    
    print("\n📝 Queries de prueba:\n")
    
    for query in test_queries:
        # Preprocesar
        query_clean = preprocess_text(query)
        
        # Vectorizar
        X = vectorizer.transform([query_clean])
        
        # Predecir
        start_time = time.time()
        prediction = model.predict(X)[0]
        proba = model.predict_proba(X)[0]
        inference_time = (time.time() - start_time) * 1000  # ms
        
        # Probabilidades por clase
        proba_dict = dict(zip(model.classes_, proba))
        confidence = max(proba)
        
        # Mostrar resultado
        emoji = "✅" if confidence >= 0.8 else "⚠️"
        print(f"{emoji} \"{query}\"")
        print(f"   → {prediction} (confidence: {confidence:.3f})")
        print(f"   Probabilities: {proba_dict}")
        print(f"   Inference time: {inference_time:.2f}ms")
        print()


def main():
    """
    Pipeline completo de entrenamiento
    """
    print("=" * 80)
    print("🚀 INTENT CLASSIFIER TRAINING")
    print("=" * 80)
    print()
    
    # 1. Cargar dataset
    df = load_dataset(DATASET_PATH)
    
    # 2. Entrenar modelo
    vectorizer, model, metrics = train_model(df)
    
    # 3. Guardar modelo
    save_model(vectorizer, model, metrics)
    
    # 4. Test de inferencia
    test_model_inference(vectorizer, model)
    
    # Resumen final
    print("=" * 80)
    print("✅ ENTRENAMIENTO COMPLETADO")
    print("=" * 80)
    print()
    print(f"📊 Métricas Finales:")
    print(f"   Test Accuracy: {metrics['test_accuracy']:.4f} ({metrics['test_accuracy']*100:.2f}%)")
    print(f"   CV Accuracy: {metrics['cv_mean']:.4f} (+/- {metrics['cv_std']:.4f})")
    print(f"   Vocab Size: {metrics['vocab_size']}")
    print(f"   Training Time: {metrics['training_time']:.2f}s")
    print()
    print(f"📁 Modelo guardado en: {MODEL_DIR.absolute()}")
    print()
    print("🎯 Próximos pasos:")
    print("   1. Revisar métricas arriba")
    print("   2. Si accuracy >= 95%: Integrar en sistema")
    print("   3. Si accuracy < 95%: Considerar feature engineering o modelo más complejo")
    print()


if __name__ == "__main__":
    main()