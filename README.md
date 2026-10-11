# FedMeta: Federated Meta-Agent System for Multi-User Learning

## 📖 Project Overview
**FedMeta** is a privacy-preserving, dynamic multi-agent system built on the **Agno** framework. It allows users to interact via **Telegram** or **AGUI**, where a central **Meta-Agent** dynamically generates specialized sub-agents to solve complex, personalized tasks. 

To continuously improve without violating user privacy, FedMeta utilizes **Federated Agent Learning (FAL)**. Instead of sharing raw user data or model weights, isolated user sessions extract generalized tool-usage heuristics and abstract problem-solving rules. These sanitized insights are pooled centrally to upgrade the global Meta-Agent's capabilities.

---

## 🏗️ Core Architecture

The system is divided into three distinct layers:
1. **The Interface Layer:** Multi-user access points via Telegram and Agno UI (AGUI).
2. **The Execution Layer (Meta-Agent):** Dynamic agent generation and personalized task execution.
3. **The Federated Learning Layer:** Local knowledge extraction and global heuristic aggregation.