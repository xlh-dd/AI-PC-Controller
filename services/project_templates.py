"""
ProjectTemplates — 项目模板系统

预定义常用项目模板，一键生成项目骨架：
  - Python Flask/FastAPI Web
  - Python 爬虫
  - React/Vue 前端
  - Node.js Express
  - Go Web
  - Rust CLI
  - 数据科学
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ProjectTemplate:
    """项目模板定义"""
    name: str
    description: str
    language: str
    files: Dict[str, str]  # 相对路径 -> 内容
    dependencies: List[str] = None
    dev_dependencies: List[str] = None
    post_commands: List[str] = None  # 生成后执行的命令


class ProjectTemplates:
    """项目模板管理器"""

    TEMPLATES = {
        "flask_api": ProjectTemplate(
            name="Flask REST API",
            description="Python Flask RESTful API with JWT auth",
            language="python",
            files={
                "app.py": '''from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, jwt_required, create_access_token
from datetime import datetime

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'your-secret-key'
jwt = JWTManager(app)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username')
    password = request.json.get('password')
    # TODO: validate credentials
    token = create_access_token(identity=username)
    return jsonify({"token": token})

@app.route('/api/items', methods=['GET'])
@jwt_required()
def get_items():
    # TODO: implement
    return jsonify({"items": []})

@app.route('/api/items', methods=['POST'])
@jwt_required()
def create_item():
    data = request.get_json()
    # TODO: implement
    return jsonify({"id": 1, "data": data}), 201

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
''',
                "requirements.txt": '''flask>=2.0
flask-jwt-extended>=4.0
python-dotenv>=0.19
''',
                ".env.example": '''JWT_SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///app.db
FLASK_ENV=development
''',
                "config.py": '''import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
''',
                "models.py": '''# TODO: Add SQLAlchemy models
''',
                "routes.py": '''# TODO: Add route definitions
''',
                "tests/test_app.py": '''import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health(client):
    rv = client.get('/health')
    assert rv.status_code == 200
    assert rv.get_json()['status'] == 'ok'
''',
            },
            dependencies=["flask", "flask-jwt-extended", "python-dotenv"],
            post_commands=["pip install -r requirements.txt"]
        ),

        "fastapi": ProjectTemplate(
            name="FastAPI",
            description="Python FastAPI with async support",
            language="python",
            files={
                "main.py": '''from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

app = FastAPI(title="API", version="1.0")
security = HTTPBearer()

class Item(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None

items_db = []

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/items", response_model=List[Item])
async def get_items():
    return items_db

@app.post("/items", response_model=Item)
async def create_item(item: Item):
    item.id = len(items_db) + 1
    items_db.append(item)
    return item

@app.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: int):
    for item in items_db:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
''',
                "requirements.txt": '''fastapi>=0.100
uvicorn[standard]>=0.23
pydantic>=2.0
''',
                "Dockerfile": '''FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
            },
            dependencies=["fastapi", "uvicorn", "pydantic"]
        ),

        "react_app": ProjectTemplate(
            name="React App",
            description="React + TypeScript + Vite",
            language="typescript",
            files={
                "package.json": '''{\n  "name": "react-app",\n  "private": true,\n  "version": "0.0.1",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "tsc && vite build",\n    "preview": "vite preview"\n  },\n  "dependencies": {\n    "react": "^18.2",\n    "react-dom": "^18.2"\n  },\n  "devDependencies": {\n    "@types/react": "^18.2",\n    "@types/react-dom": "^18.2",\n    "@vitejs/plugin-react": "^4.0",\n    "typescript": "^5.0",\n    "vite": "^5.0"\n  }\n}\n''',
                "index.html": '''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>React App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
''',
                "src/main.tsx": '''import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
''',
                "src/App.tsx": '''import { useState } from 'react'
import './App.css'

function App() {
  const [count, setCount] = useState(0)

  return (
    <div className="App">
      <h1>React + TypeScript + Vite</h1>
      <button onClick={() => setCount(c => c + 1)}>
        Count: {count}
      </button>
    </div>
  )
}

export default App
''',
                "src/App.css": '''.App {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
  text-align: center;
}
''',
                "src/index.css": ''':root {
  font-family: Inter, system-ui, sans-serif;
  line-height: 1.5;
  font-weight: 400;
}
''',
                "tsconfig.json": '''{\n  "compilerOptions": {\n    "target": "ES2020",\n    "useDefineForClassFields": true,\n    "lib": ["ES2020", "DOM", "DOM.Iterable"],\n    "module": "ESNext",\n    "skipLibCheck": true,\n    "moduleResolution": "bundler",\n    "allowImportingTsExtensions": true,\n    "resolveJsonModule": true,\n    "isolatedModules": true,\n    "noEmit": true,\n    "jsx": "react-jsx",\n    "strict": true,\n    "noUnusedLocals": true,\n    "noUnusedParameters": true,\n    "noFallthroughCasesInSwitch": true\n  },\n  "include": ["src"],\n  "references": [{ "path": "./tsconfig.node.json" }]\n}\n''',
                "vite.config.ts": '''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
''',
            },
            dependencies=["react", "react-dom"],
            dev_dependencies=["vite", "@vitejs/plugin-react", "typescript", "@types/react", "@types/react-dom"],
            post_commands=["npm install"]
        ),

        "vue_app": ProjectTemplate(
            name="Vue App",
            description="Vue 3 + TypeScript + Vite",
            language="typescript",
            files={
                "package.json": '''{\n  "name": "vue-app",\n  "private": true,\n  "version": "0.0.1",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "vue-tsc && vite build",\n    "preview": "vite preview"\n  },\n  "dependencies": {\n    "vue": "^3.3"\n  },\n  "devDependencies": {\n    "@vitejs/plugin-vue": "^4.0",\n    "typescript": "^5.0",\n    "vite": "^5.0",\n    "vue-tsc": "^1.8"\n  }\n}\n''',
                "index.html": '''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Vue App</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
''',
                "src/main.ts": '''import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')
''',
                "src/App.vue": '''<script setup lang="ts">
import { ref } from 'vue'

const count = ref(0)
</script>

<template>
  <div class="app">
    <h1>Vue 3 + TypeScript + Vite</h1>
    <button @click="count++">Count: {{ count }}</button>
  </div>
</template>

<style scoped>
.app {
  text-align: center;
  padding: 2rem;
}
</style>
''',
                "src/style.css": ''':root {
  font-family: Inter, system-ui, sans-serif;
}
''',
            },
            dependencies=["vue"],
            dev_dependencies=["vite", "@vitejs/plugin-vue", "typescript", "vue-tsc"],
            post_commands=["npm install"]
        ),

        "python_scraper": ProjectTemplate(
            name="Python 爬虫",
            description="Scrapy-like crawler with requests + BeautifulSoup",
            language="python",
            files={
                "scraper.py": '''import requests
from bs4 import BeautifulSoup
import json
import time
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional

class WebScraper:
    def __init__(self, base_url: str, delay: float = 1.0):
        self.base_url = base_url
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0'
        })
        self.visited = set()

    def fetch(self, url: str) -> Optional[BeautifulSoup]:
        if url in self.visited:
            return None
        self.visited.add(url)

        try:
            time.sleep(self.delay)
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def extract_links(self, soup: BeautifulSoup, base: str) -> List[str]:
        links = []
        for a in soup.find_all('a', href=True):
            href = urljoin(base, a['href'])
            if urlparse(href).netloc == urlparse(self.base_url).netloc:
                links.append(href)
        return links

    def parse(self, soup: BeautifulSoup) -> Dict:
        # TODO: implement parsing logic
        return {
            "title": soup.title.text if soup.title else "",
            "links": len(soup.find_all('a')),
        }

    def run(self, start_url: str = None):
        url = start_url or self.base_url
        soup = self.fetch(url)
        if soup:
            data = self.parse(soup)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return data
        return None

if __name__ == '__main__':
    scraper = WebScraper('https://example.com')
    scraper.run()
''',
                "requirements.txt": '''requests>=2.28
beautifulsoup4>=4.11
lxml>=4.9
''',
            },
            dependencies=["requests", "beautifulsoup4", "lxml"]
        ),

        "go_api": ProjectTemplate(
            name="Go API",
            description="Go Gin REST API",
            language="go",
            files={
                "main.go": '''package main

import (
	"net/http"
	"github.com/gin-gonic/gin"
)

type Item struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

var items = []Item{}

func main() {
	r := gin.Default()

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	r.GET("/items", func(c *gin.Context) {
		c.JSON(http.StatusOK, items)
	})

	r.POST("/items", func(c *gin.Context) {
		var item Item
		if err := c.ShouldBindJSON(&item); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		item.ID = len(items) + 1
		items = append(items, item)
		c.JSON(http.StatusCreated, item)
	})

	r.Run(":8080")
}
''',
                "go.mod": '''module api

go 1.21

require github.com/gin-gonic/gin v1.9.1
''',
                "Dockerfile": '''FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o main .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/main .
EXPOSE 8080
CMD ["./main"]
''',
            },
            dependencies=["github.com/gin-gonic/gin"],
            post_commands=["go mod tidy"]
        ),

        "rust_cli": ProjectTemplate(
            name="Rust CLI",
            description="Rust CLI with clap",
            language="rust",
            files={
                "Cargo.toml": '''[package]
name = "cli"
version = "0.1.0"
edition = "2021"

[dependencies]
clap = { version = "4.0", features = ["derive"] }
anyhow = "1.0"
tokio = { version = "1.0", features = ["full"] }
''',
                "src/main.rs": '''use clap::{Parser, Subcommand};
use anyhow::Result;

#[derive(Parser)]
#[command(name = "cli")]
#[command(about = "A CLI tool")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Hello { name: Option<String> },
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Hello { name } => {
            println!("Hello, {}!", name.unwrap_or_else(|| "World".to_string()));
        }
    }

    Ok(())
}
''',
            },
            post_commands=["cargo build"]
        ),

        "data_science": ProjectTemplate(
            name="数据科学",
            description="Jupyter + Pandas + Matplotlib",
            language="python",
            files={
                "notebook.ipynb": '''{\n "cells": [\n  {\n   "cell_type": "code",\n   "execution_count": null,\n   "metadata": {},\n   "outputs": [],\n   "source": [\n    "import pandas as pd\\n",\n    "import numpy as np\\n",\n    "import matplotlib.pyplot as plt\\n",\n    "import seaborn as sns\\n",\n    "\\n",\n    "# 设置中文字体\\n",\n    "plt.rcParams['font.sans-serif'] = ['SimHei']\\n",\n    "plt.rcParams['axes.unicode_minus'] = False"\n   ]\n  },\n  {\n   "cell_type": "code",\n   "execution_count": null,\n   "metadata": {},\n   "outputs": [],\n   "source": [\n    "# 加载数据\\n",\n    "df = pd.read_csv('data.csv')\\n",\n    "df.head()"\n   ]\n  }\n ],\n "metadata": {\n  "kernelspec": {\n   "display_name": "Python 3",\n   "language": "python",\n   "name": "python3"\n  }\n },\n "nbformat": 4,\n "nbformat_minor": 4\n}\n''',
                "requirements.txt": '''pandas>=2.0
numpy>=1.24
matplotlib>=3.7
seaborn>=0.12
jupyter>=1.0
scikit-learn>=1.3
''',
                "data/.gitkeep": "",
                "scripts/analyze.py": '''import pandas as pd
import matplotlib.pyplot as plt

def analyze_data(file_path: str):
    df = pd.read_csv(file_path)
    print(f"Shape: {df.shape}")
    print(f"\\nInfo:")
    print(df.info())
    print(f"\\nDescribe:")
    print(df.describe())

    # 保存统计图
    df.hist(figsize=(10, 8))
    plt.tight_layout()
    plt.savefig('output/histogram.png')
    print("Saved: output/histogram.png")

if __name__ == '__main__':
    analyze_data('data/data.csv')
''',
            },
            dependencies=["pandas", "numpy", "matplotlib", "seaborn", "jupyter", "scikit-learn"]
        ),
    }

    @classmethod
    def list_templates(cls) -> List[Dict]:
        """列出所有模板"""
        return [
            {
                "id": tid,
                "name": t.name,
                "description": t.description,
                "language": t.language,
                "files_count": len(t.files)
            }
            for tid, t in cls.TEMPLATES.items()
        ]

    @classmethod
    def get_template(cls, template_id: str) -> Optional[ProjectTemplate]:
        """获取模板"""
        return cls.TEMPLATES.get(template_id)

    @classmethod
    def generate(cls, template_id: str, output_dir: str, project_name: str = None) -> Dict:
        """生成项目

        Returns:
            {"success": bool, "files": [...], "errors": [...]}
        """
        template = cls.get_template(template_id)
        if not template:
            return {"success": False, "errors": [f"模板不存在: {template_id}"]}

        project_name = project_name or template_id
        project_dir = os.path.join(output_dir, project_name)

        os.makedirs(project_dir, exist_ok=True)

        created = []
        errors = []

        for rel_path, content in template.files.items():
            try:
                file_path = os.path.join(project_dir, rel_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                created.append(rel_path)
            except Exception as e:
                errors.append(f"{rel_path}: {e}")

        return {
            "success": len(errors) == 0,
            "files": created,
            "errors": errors,
            "project_dir": project_dir,
            "template": template
        }
