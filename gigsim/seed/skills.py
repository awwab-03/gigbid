"""Skill taxonomy used by the synthetic data generator.

Every skill has a canonical name, a category, *paraphrases* (how a case study or a vague
client post describes the skill without naming it) and, where relevant, a code signal
(the import or config line that reveals the skill inside source code).

Paraphrases are what make the corpus hard for naive dense retrieval: a case study can prove
"Celery" without ever writing the word, and only the code chunk names it.
"""

from __future__ import annotations

SKILLS: dict[str, dict] = {
    # ---------------------------------------------------------------- ML / AI
    "Python": {"cat": "core", "para": ["scripting the pipeline end to end"], "code": "import sys"},
    "PyTorch": {"cat": "ml", "para": ["a custom neural network trained on GPUs", "a deep model written with autograd"], "code": "import torch\nimport torch.nn as nn"},
    "TensorFlow": {"cat": "ml", "para": ["a Keras-style deep network"], "code": "import tensorflow as tf"},
    "scikit-learn": {"cat": "ml", "para": ["classical models with cross-validated pipelines"], "code": "from sklearn.pipeline import Pipeline\nfrom sklearn.model_selection import cross_val_score"},
    "XGBoost": {"cat": "ml", "para": ["gradient-boosted trees tuned with early stopping"], "code": "import xgboost as xgb"},
    "LightGBM": {"cat": "ml", "para": ["a fast leaf-wise boosted tree model"], "code": "import lightgbm as lgb"},
    "pandas": {"cat": "core", "para": ["dataframe wrangling of messy exports"], "code": "import pandas as pd"},
    "NumPy": {"cat": "core", "para": ["vectorised array maths"], "code": "import numpy as np"},
    "NLP": {"cat": "ml", "para": ["understanding free-text customer messages", "text classification of support tickets"], "code": "from sklearn.feature_extraction.text import TfidfVectorizer"},
    "Hugging Face Transformers": {"cat": "ml", "para": ["a pretrained language model fine-tuned on in-house text"], "code": "from transformers import AutoModelForSequenceClassification, AutoTokenizer"},
    "LangChain": {"cat": "ml", "para": ["chained LLM calls with tool use"], "code": "from langchain_core.prompts import ChatPromptTemplate"},
    "LangGraph": {"cat": "ml", "para": ["a stateful agent graph with branches and checkpoints"], "code": "from langgraph.graph import StateGraph, START, END"},
    "RAG": {"cat": "ml", "para": ["an assistant that answers from the company's own documents with citations", "grounding model answers in retrieved passages"], "code": "def retrieve_then_generate(question, index):"},
    "LLM fine-tuning": {"cat": "ml", "para": ["adapting an open model to the client's tone with LoRA adapters"], "code": "from peft import LoraConfig, get_peft_model"},
    "OpenAI API": {"cat": "ml", "para": ["calls to a hosted chat-completion model"], "code": "from openai import OpenAI"},
    "Computer vision": {"cat": "ml", "para": ["reading product photos automatically", "detecting defects in camera frames"], "code": "import cv2"},
    "OpenCV": {"cat": "ml", "para": ["frame-by-frame image preprocessing"], "code": "import cv2"},
    "YOLO": {"cat": "ml", "para": ["a real-time single-shot object detector"], "code": "from ultralytics import YOLO"},
    "Time series forecasting": {"cat": "ml", "para": ["predicting next month's demand from weekly history", "seasonal sales projections"], "code": "from statsmodels.tsa.holtwinters import ExponentialSmoothing"},
    "Prophet": {"cat": "ml", "para": ["an additive trend-plus-holiday forecaster"], "code": "from prophet import Prophet"},
    "MLflow": {"cat": "ml", "para": ["experiment tracking with a model registry"], "code": "import mlflow"},
    "FAISS": {"cat": "ml", "para": ["an in-memory nearest-neighbour index over embeddings"], "code": "import faiss"},
    "Pinecone": {"cat": "ml", "para": ["a managed vector index", "a hosted similarity-search service"], "code": "from pinecone import Pinecone"},
    "spaCy": {"cat": "ml", "para": ["rule-plus-statistical entity extraction"], "code": "import spacy"},
    "Recommendation systems": {"cat": "ml", "para": ["suggesting the next product a shopper is likely to buy"], "code": "from implicit.als import AlternatingLeastSquares"},
    "Model evaluation": {"cat": "ml", "para": ["honest hold-out testing with precision and recall reported"], "code": "from sklearn.metrics import classification_report"},
    "Churn prediction": {"cat": "ml", "para": ["flagging customers likely to cancel"], "code": "churn_label = df['cancelled_within_90d']"},
    "ONNX": {"cat": "ml", "para": ["exporting the model to a portable runtime for CPU inference"], "code": "import onnxruntime as ort"},
    "AWS SageMaker": {"cat": "ml", "para": ["managed training jobs and a hosted inference endpoint on Amazon"], "code": "import sagemaker"},
    # ---------------------------------------------------------------- shared infra
    "Docker": {"cat": "infra", "para": ["a containerised build that runs the same everywhere"], "code": "FROM python:3.11-slim"},
    "Kubernetes": {"cat": "infra", "para": ["container orchestration with autoscaling pods"], "code": "apiVersion: apps/v1\nkind: Deployment"},
    "AWS": {"cat": "infra", "para": ["hosting on Amazon's cloud with object storage and managed databases"], "code": "import boto3"},
    "CI/CD": {"cat": "infra", "para": ["every push tested and deployed automatically"], "code": "on: [push]\njobs:\n  test:"},
    "Celery": {"cat": "infra", "para": ["a background task queue that retried failed jobs", "asynchronous workers pulling tasks off a broker"], "code": "from celery import Celery"},
    "Redis": {"cat": "infra", "para": ["an in-memory cache in front of the database"], "code": "import redis"},
    "Airflow": {"cat": "data", "para": ["scheduled DAGs that orchestrated the nightly loads"], "code": "from airflow import DAG"},
    "FastAPI": {"cat": "web", "para": ["a typed async Python API with auto-generated docs"], "code": "from fastapi import FastAPI"},
    # ---------------------------------------------------------------- web
    "JavaScript": {"cat": "web", "para": ["interactive browser code"], "code": "document.addEventListener('DOMContentLoaded', () => {"},
    "TypeScript": {"cat": "web", "para": ["strictly typed front-end code"], "code": "interface Props {"},
    "React": {"cat": "web", "para": ["a component-based single-page interface"], "code": "import { useState } from 'react'"},
    "Next.js": {"cat": "web", "para": ["server-rendered pages with file-based routing"], "code": "export async function getServerSideProps()"},
    "Vue.js": {"cat": "web", "para": ["a reactive template-driven front end"], "code": "import { createApp } from 'vue'"},
    "Node.js": {"cat": "web", "para": ["a server-side JavaScript runtime"], "code": "const http = require('http')"},
    "Express": {"cat": "web", "para": ["a minimal JavaScript HTTP router with middleware"], "code": "const express = require('express')"},
    "NestJS": {"cat": "web", "para": ["a modular, decorator-based TypeScript backend"], "code": "import { Module } from '@nestjs/common'"},
    "Django": {"cat": "web", "para": ["a batteries-included Python web framework with an admin panel"], "code": "from django.db import models"},
    "Flask": {"cat": "web", "para": ["a micro Python web app"], "code": "from flask import Flask"},
    "PostgreSQL": {"cat": "data", "para": ["a relational database with proper migrations and indexes"], "code": "CREATE INDEX CONCURRENTLY"},
    "MongoDB": {"cat": "web", "para": ["a document store for flexible records"], "code": "from pymongo import MongoClient"},
    "GraphQL": {"cat": "web", "para": ["a single typed query endpoint clients shape themselves"], "code": "type Query {"},
    "REST API": {"cat": "web", "para": ["versioned HTTP endpoints for the mobile app"], "code": "@app.get('/api/v1/items')"},
    "Tailwind CSS": {"cat": "web", "para": ["utility-first styling"], "code": "className=\"flex items-center gap-2\""},
    "Stripe": {"cat": "web", "para": ["subscription billing and checkout", "card payments with webhooks for renewals"], "code": "import Stripe from 'stripe'"},
    "WebSockets": {"cat": "web", "para": ["live updates pushed to the browser without refresh"], "code": "const ws = new WebSocket(url)"},
    "Jest": {"cat": "web", "para": ["unit tests for every component"], "code": "describe('Cart', () => {"},
    "Playwright": {"cat": "web", "para": ["browser tests that click through the real flows"], "code": "import { test, expect } from '@playwright/test'"},
    "Shopify": {"cat": "web", "para": ["a hosted storefront with a custom theme"], "code": "{% section 'product-template' %}"},
    "WordPress": {"cat": "web", "para": ["a PHP CMS site with custom plugins"], "code": "add_action('init', 'register_cpt');"},
    "Firebase": {"cat": "web", "para": ["Google's realtime backend with hosted auth"], "code": "import { initializeApp } from 'firebase/app'"},
    "Supabase": {"cat": "web", "para": ["an open-source Postgres backend with row-level security"], "code": "import { createClient } from '@supabase/supabase-js'"},
    "Prisma": {"cat": "web", "para": ["a typed ORM with schema migrations"], "code": "model User {"},
    "OAuth": {"cat": "web", "para": ["sign in with Google and GitHub"], "code": "authorization_code"},
    # ---------------------------------------------------------------- data analytics
    "SQL": {"cat": "data", "para": ["hand-written queries with window functions"], "code": "SELECT customer_id, SUM(amount) OVER (PARTITION BY region)"},
    "BigQuery": {"cat": "data", "para": ["Google's serverless warehouse"], "code": "from google.cloud import bigquery"},
    "Snowflake": {"cat": "data", "para": ["a cloud warehouse with separate compute and storage"], "code": "import snowflake.connector"},
    "Redshift": {"cat": "data", "para": ["Amazon's columnar warehouse"], "code": "COPY sales FROM 's3://"},
    "dbt": {"cat": "data", "para": ["version-controlled SQL transformation models with tests", "a modelling layer of tested SQL views"], "code": "{{ config(materialized='incremental') }}"},
    "Power BI": {"cat": "data", "para": ["Microsoft's report builder with DAX measures"], "code": "Total Sales = SUM(Sales[Amount])"},
    "Tableau": {"cat": "data", "para": ["drag-and-drop visual workbooks published for the team"], "code": "-- Tableau calculated field: IF [Profit] < 0 THEN 'Loss' END"},
    "Looker Studio": {"cat": "data", "para": ["free Google dashboards connected to Sheets"], "code": "-- Looker Studio blended data source"},
    "Excel": {"cat": "data", "para": ["spreadsheet models with pivot tables and lookups"], "code": "=XLOOKUP(A2, Orders!A:A, Orders!F:F)"},
    "Google Sheets": {"cat": "data", "para": ["shared spreadsheets with Apps Script automation"], "code": "function onEdit(e) {"},
    "ETL": {"cat": "data", "para": ["extracting, cleaning and loading data from several sources nightly"], "code": "def extract(): ...\ndef transform(df): ...\ndef load(df): ..."},
    "Data cleaning": {"cat": "data", "para": ["deduplicating and standardising messy records"], "code": "df = df.drop_duplicates(subset=['email']).dropna(subset=['order_id'])"},
    "Dashboarding": {"cat": "data", "para": ["a single page of KPIs the managers check every morning"], "code": "-- dashboard KPI tiles"},
    "Statistics": {"cat": "data", "para": ["confidence intervals and significance tests"], "code": "from scipy import stats"},
    "A/B testing": {"cat": "data", "para": ["controlled experiments comparing two variants"], "code": "stats.chi2_contingency(table)"},
    "R": {"cat": "data", "para": ["tidyverse analysis scripts"], "code": "library(dplyr)"},
    "Fivetran": {"cat": "data", "para": ["managed connectors syncing SaaS sources into the warehouse"], "code": "# fivetran connector: hubspot -> raw.hubspot"},
    "Metabase": {"cat": "data", "para": ["an open-source BI tool for self-serve questions"], "code": "-- Metabase native question"},
    "GA4": {"cat": "data", "para": ["web analytics events and conversion funnels"], "code": "event_name = 'purchase'"},
    "Data visualization": {"cat": "data", "para": ["clear charts that tell one story each"], "code": "import matplotlib.pyplot as plt"},
    "Forecasting": {"cat": "data", "para": ["projecting revenue for next quarter"], "code": "forecast = model.predict(future)"},
}

# Skills the personas never have: used to create jobs a persona should skip.
FOREIGN_SKILLS = [
    "Go", "Rust", "Unity", "Solidity", "Swift", "Kotlin", "C++ embedded firmware", "SAP ABAP",
    "Salesforce Apex", "Unreal Engine", "3D modelling in Blender", "Video editing", "Logo design",
    "Copywriting", "Mobile game development", "PLC programming", "Flutter", "Elixir",
]


def paraphrase(skill: str, idx: int = 0) -> str:
    spec = SKILLS.get(skill)
    if not spec:
        return skill
    paras = spec["para"]
    return paras[idx % len(paras)]


def code_signal(skill: str) -> str:
    spec = SKILLS.get(skill)
    return spec["code"] if spec else f"# uses {skill}"
