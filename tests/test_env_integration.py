#!/usr/bin/env python3

import os
from backend.core.config import settings

print("🔍 Environment Variables Test:")
print("-" * 40)

print(f"GROQ_API_KEY from os.getenv: {os.getenv('GROQ_API_KEY', 'NOT_SET')[:20]}...")
print(f"OPENAI_API_KEY from os.getenv: {os.getenv('OPENAI_API_KEY', 'NOT_SET')[:20]}...")

print(f"\nSettings from config:")
print(f"settings.groq_api_key: {settings.groq_api_key[:20]}...")
print(f"settings.openai_api_key: {settings.openai_api_key[:20]}...")
print(f"settings.use_groq: {settings.use_groq}")
print(f"settings.use_openai: {settings.use_openai}")

print(f"\nTrying to create Groq client with explicit API key:")
try:
    from langchain_groq import ChatGroq
    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model="llama-3.1-70b-versatile", 
        temperature=0.1
    )
    print("✅ Groq client created successfully with explicit API key")
except Exception as e:
    print(f"❌ Groq client creation failed: {e}")