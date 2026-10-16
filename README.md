# 🛡️ Agent Shield: A Middleware Framework for Securing Agentic AI Systems

> **Final Year B.Tech Capstone Project**  
> **Department of Computer Science & Engineering**  
> **Meerut Institute of Engineering & Technology (MIET), Meerut**  
> **Under the Guidance of:** Mr. Varun Kaushik

---

## 👥 Authors & Project Team

- **Vidushi Agarwal** — _University Roll No: 2300680110116_
- **Vanshika Rastogi** — _University Roll No: 2300680110111_
- **Suryansh Singh** — _University Roll No: 2300680100288_
- **Shubh Sharma** — _University Roll No: 2300680100276_

---

## 📌 Abstract

Contemporary Large Language Model (LLM) agents built on frameworks like LangGraph plan multi-step tasks, invoke local tools, and communicate with external APIs autonomously. However, because their behavior is governed by natural language rather than deterministic code, they are inherently susceptible to **Direct & Indirect Prompt Injection**, **Jailbreaks**, **Privilege Escalation**, and **Data Exfiltration**.

Existing safety mechanisms rely heavily on model-level alignment training, which can be bypassed through adversarial phrasing. **Agent Shield** introduces an independent, framework-agnostic **AI Security Gateway** positioned between client interfaces, agent orchestrators, and tool execution environments. Agent Shield intercepts prompts, reasoning steps, and tool calls to compute a normalized **Risk Score (0–100)**, enforcing a four-band policy: **ALLOW**, **WARN**, **APPROVE** (Human-in-the-Loop), and **BLOCK**.

---

## 🏗️ System Architecture

```text
[User / React Client]
         │ (HTTP / Axios)
         ▼
[FastAPI Security Gateway]
         │
   ┌─────┴────────────────────────────────────────────────────────┐
   │ 1. INBOUND LAYER (Agent Shield Layer 1)                      │
   │    ├── Prompt Scanner (Signature Heuristics & Exfiltration)  │
   │    └── Jailbreak Detector (all-MiniLM-L6-v2 Semantic Match)  │
   │    ► Peak Threat Policy: Immediate BLOCK if Risk >= 80      │
   └─────┬────────────────────────────────────────────────────────┘
         │
         ▼
   ┌─────┴────────────────────────────────────────────────────────┐
   │ 2. AGENTIC ORCHESTRATION LAYER (LangGraph Core)              │
   │    ├── Autonomous LLM ReAct Agent (Groq / Gemini)            │
   │    │                                                         │
   │    ▼ 3. TOOL INTERCEPTION LAYER (Agent Shield Layer 2)       │
   │    ├── Policy ACL & Parameter Validator                      │
   │    ├── Dynamic Session Capability Leases                     │
   │    └── If Risk 50–80: FREEZE state for Human Review (HITL)   │
   │                                                              │
   │    ▼ 4. OUTBOUND LAYER (Agent Shield Layer 3)                │
   │    └── Response Scanner (API Key, Secret, & PII Redactor)   │
   └─────┬────────────────────────────────────────────────────────┘
         ▼
[Audit Database (PostgreSQL / SQLite) & Telemetry Dashboard]
```
