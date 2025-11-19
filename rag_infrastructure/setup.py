"""
📦 SETUP PARA INSTALAR COMO PAQUETE
===================================

Permite instalar la infraestructura RAG como un paquete Python
"""

from setuptools import setup, find_packages

setup(
    name="rag-infrastructure",
    version="1.0.0",
    description="Infraestructura RAG reutilizable con ingesta, búsqueda y monitoreo",
    author="Tu Nombre",
    packages=find_packages(),
    install_requires=[
        "llama-index>=0.9.0",
        "openai>=1.0.0",
        "psycopg2-binary>=2.9.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "metadata": ["PyPDF2>=3.0.0", "langdetect>=1.0.9"],
        "monitoring": ["rich>=13.0.0"],
    },
    python_requires=">=3.8",
)













