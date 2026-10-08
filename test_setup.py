import pypdf
import faiss
import sentence_transformers
from openai import OpenAI

print("pypdf:", pypdf.__version__)
print("faiss:", faiss.__version__)
print("sentence-transformers:", sentence_transformers.__version__)

client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
try:
    models = client.models.list()
    print("\nModeli u LM Studio:")
    for m in models.data:
        print(" -", m.id)
except Exception as e:
    print("\nLM Studio nije dostupan:", e)
