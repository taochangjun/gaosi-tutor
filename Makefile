.PHONY: help install check init-db smoke smoke-llm smoke-rag smoke-hybrid rag-index db-up db-down start

help:
	@echo "gaosi-tutor 命令"
	@echo ""
	@echo "  make install     安装前后端依赖"
	@echo "  make db-up       启动 Docker MySQL（端口 3307）"
	@echo "  make init-db     创建库表 + 灌入 21 讲"
	@echo "  make check       环境检查"
	@echo "  make smoke       冒烟（不调 LLM）"
	@echo "  make smoke-llm   冒烟（需 API Key）"
	@echo "  make smoke-rag   RAG 冒烟（切块/索引/检索）"
	@echo "  make smoke-hybrid 混合检索练习验收（BM25+RRF，需先实现）"
	@echo "  make rag-index   全量同步家庭笔记到向量库"
	@echo "  make start       启动前后端"

install:
	cd backend && (test -d venv || python3 -m venv venv) && ./venv/bin/pip install -r requirements.txt
	cd frontend && npm install

db-up:
	docker compose up -d

db-down:
	docker compose down

init-db:
	cd backend && ./venv/bin/python -m scripts.init_db

check:
	cd backend && ./venv/bin/python -m scripts.check_env

smoke:
	cd backend && ./venv/bin/python -m scripts.smoke_test --dry

smoke-llm:
	cd backend && ./venv/bin/python -m scripts.smoke_test

smoke-rag:
	cd backend && ./venv/bin/python -m scripts.smoke_rag

smoke-hybrid:
	cd backend && ./venv/bin/python -m scripts.smoke_hybrid_rag

rag-index:
	cd backend && ./venv/bin/python -c "from app.database import SessionLocal; from app.agent.rag.indexer import index_all_notes; db=SessionLocal(); print(index_all_notes(db)); db.close()"

start:
	./start.sh
