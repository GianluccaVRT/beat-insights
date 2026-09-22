.PHONY: help start start-db start-ollama stop

VENV_STREAMLIT := .venv/bin/streamlit

help:
	@echo "make start   -- sobe Postgres (docker) + confere Ollama + roda o explorer (Streamlit, foreground)"
	@echo "make stop    -- para o Postgres (docker compose stop, sem apagar dados)"

# Ordem importa: Postgres precisa estar healthy e Ollama respondendo antes do
# explorer.py subir (chat flutuante chama Ollama, resto da tela lê do Postgres).
# Streamlit fica em foreground de propósito -- Ctrl+C encerra ele sozinho, sem
# derrubar Postgres/Ollama junto (ver README, "Como interromper com segurança").
start: start-db start-ollama
	@if [ ! -x "$(VENV_STREAMLIT)" ]; then \
		echo "==> .venv não encontrado -- rode primeiro: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"; \
		exit 1; \
	fi
	@echo "==> Subindo o explorer (Streamlit) em http://localhost:8501 -- Ctrl+C pra encerrar"
	$(VENV_STREAMLIT) run src/explorer.py

start-db:
	@echo "==> Subindo Postgres (docker compose)"
	@docker compose up -d
	@echo "==> Esperando Postgres ficar healthy..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' beat-insights-db 2>/dev/null)" = "healthy" ]; do sleep 1; done
	@echo "==> Postgres pronto."

start-ollama:
	@if curl -fs -o /dev/null http://localhost:11434/api/version; then \
		echo "==> Ollama já está rodando."; \
	else \
		echo "==> Ollama não respondeu em localhost:11434 -- tentando iniciar via 'brew services'..."; \
		brew services start ollama || echo "==> Não consegui iniciar o Ollama automaticamente -- rode 'ollama serve' manualmente (chat flutuante do explorer não funciona sem ele, resto da tela funciona normalmente)."; \
		sleep 2; \
	fi

stop:
	@echo "==> Parando Postgres (docker compose stop, sem apagar dados -- volume pgdata continua intacto)"
	@docker compose stop
