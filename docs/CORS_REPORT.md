# CORS Report — HOTFIX PR009.3

Data da validação: 2026-09-17

## Escopo

Correção exclusiva da comunicação entre:

- Frontend: `https://brobond-studio-web.onrender.com`
- Backend: `https://brobond-ai-api.onrender.com`
- Desenvolvimento local: `http://localhost:3000`

## Implementação

O `CORSMiddleware` está registrado em `backend/app/main.py` e usa a lista produzida por `settings.cors_origin_list`.

Configuração efetiva:

- `allow_origins`: somente as origens configuradas em `BROBOND_CORS_ORIGINS`;
- `allow_credentials=True`;
- `allow_methods=["*"]`;
- `allow_headers=["*"]`;
- `expose_headers=["x-brobond-trace"]`.

Não há wildcard em `allow_origins`, mantendo a configuração compatível e segura com credenciais.

## Parser da variável de ambiente

`backend/app/core/config.py` trata `BROBOND_CORS_ORIGINS` como uma lista separada por vírgulas. O parser remove espaços nas extremidades e ignora entradas vazias.

Entrada:

```text
https://brobond-studio-web.onrender.com,http://localhost:3000
```

Resultado:

```python
[
    "https://brobond-studio-web.onrender.com",
    "http://localhost:3000",
]
```

O mesmo valor está declarado para a API em `render.yaml`.

## Validação automatizada

Arquivo: `backend/tests/test_cors.py`

Comando executado:

```bash
pytest -q backend/tests/test_cors.py
```

Resultado: **5 testes aprovados**.

| Requisição preflight | Status | Allow-Origin | Credentials | Methods |
|---|---:|---|---|---|
| `OPTIONS /api/v1/health` | 200 | origem do frontend | `true` | inclui `GET` |
| `OPTIONS /api/v1/assets` | 200 | origem do frontend | `true` | inclui `GET` |
| `OPTIONS /api/v1/personas` | 200 | origem do frontend | `true` | inclui `GET` |

Também foram validados o parser, a ausência de `*` na lista de origens e o header `Access-Control-Expose-Headers: x-brobond-trace` em resposta simples.

## Definition of Done

- Preflight do frontend autorizado nos três endpoints: **OK**.
- Health check local `GET /api/v1/health`: **200**.
- Assets e personas: preflight **200**; as chamadas de dados continuam sujeitas à autenticação normal da API.
- Configuração do Render alinhada ao domínio público do frontend: **OK**.
- Status Center pode consultar o health endpoint sem bloqueio CORS: **OK**.

A confirmação do estado **Online** no ambiente público depende do deploy desta alteração no Render.
