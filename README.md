# Jarvis PC Assistant

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=ollama&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)

**Personal assistant for your PC.** Control your computer by voice or text — open apps and websites, and step into WhatsApp, Telegram and Discord conversations through the browser to read and reply to messages.

## Stack

- Python
- LLM with tool calling to interpret natural language: **Ollama** (local, free) or **Gemini** (API)
- Playwright (browser automation for WhatsApp Web / Telegram Web / Discord)
- faster-whisper (local speech recognition) + edge-tts (Portuguese neural voice)
- rich (terminal UI)

## Features

- Open PC applications by name (`"abre o Spotify"` — "open Spotify")
- Open websites in the browser (`"abre o YouTube"` — "open YouTube")
- Search the web
- Enter a conversation (WhatsApp, Telegram or Discord) and read the latest messages
- Reply to a specific person in a conversation
- Voice or text commands

> **Note:** Jarvis is designed for European Portuguese (pt-PT). Voice commands and spoken replies are in Portuguese; example commands below are shown in Portuguese with an English translation.
