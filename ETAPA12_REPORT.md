# ETAPA 12 — STORAGE (MinIO/S3)

Relatório técnico. Escopo: camada de armazenamento de objetos.

**Resultado:** `StorageService` deixou de ser write-only. Os quatro pontos que recusavam
trabalhar com object storage ligado foram religados. `storage.py` foi de **61% para 100%** de
cobertura — incluindo o guard de *path traversal*, que jamais havia sido executado por teste
algum. `633 → 692` testes. Zero arquivos deletados.

---

## 1. Auditoria — tudo medido antes de escrever

| # | Achado | Como foi medido |
| --- | --- | --- |
| C1 | `StorageService` não tinha `download`, `delete` nem `exists` | leitura integral de `storage.py` (64 l): só `save`, `save_path`, `signed_url`, `local_path` |
| C2 | **Quatro** caminhos recusavam 501/RuntimeError com storage ligado | `grep` em `main.py` (condicionamento, export) e `queue.py` (LoRA, referência) |
| C3 | O ramo S3 **nunca** foi executado por teste algum | `storage.py` em 61%; linhas faltantes 32-33, 41-49, 53 |
| C4 | O guard de *path traversal* nunca executou | linhas 57-61 entre as faltantes; `storage_enabled` só é posto `False` nos testes |
| C5 | Bucket nunca é garantido | nenhum `head_bucket`/`create_bucket` no módulo |
| C6 | TTL de presigned hardcoded em três lugares | `ExpiresIn=3600` literal ×3 |
| C7 | Cliente boto3 e `mkdir` construídos no `__init__` | efeito colateral de import |
| C8 | `minio` é dependência morta | já documentado em `requirements.txt`; o código usa boto3 |

### A causa dos 501 era uma só

```
main.py:  "MinIO preprocessing adapter is not enabled"        → 501
main.py:  "MinIO source download adapter is not enabled ..."  → 501
queue.py: "MinIO LoRA download adapter is required ..."       → RuntimeError
queue.py: "MinIO reference download adapter is required ..."  → RuntimeError
```

Nenhum dos quatro era uma decisão de produto. Os três precisam de **bytes num sistema de
arquivos** para trabalhar, e `StorageService` não oferecia uma função que os trouxesse. O 501
era a ausência de um método, não uma escolha.

### O guard funcionava — só nunca tinha sido provado

Executado diretamente antes de tocar no código:

```
'ws1/img.png'            -> ACEITO
'../etc/passwd'          -> bloqueado (ValueError: Invalid asset path)
'../../etc/passwd'       -> bloqueado
'/etc/passwd'            -> bloqueado
'ws1/../../etc/passwd'   -> bloqueado
''                       -> bloqueado
'.'                      -> bloqueado
```

O controle é correto. O problema era que **nada o garantia**: uma refatoração futura podia
removê-lo e a suíte continuaria verde.

---

## 2. O que foi feito

### 2.1 Os primitivos que faltavam

| Método | Modo local | Modo S3/MinIO |
| --- | --- | --- |
| `download(key, destination)` | devolve o arquivo já local, sem cópia | `download_file` |
| `exists(key)` | `Path.is_file()` | `head_object` |
| `delete(key)` | `unlink` guardado por `local_path` | `delete_object` |
| `upload_path(source, key, ct)` | cópia só se a chave diferir | upload para chave **do chamador** |
| `ensure_bucket()` | garante o diretório | `head_bucket` → `create_bucket` |

`download` é o que destrava os quatro 501. `ensure_bucket` elimina o `NoSuchBucket` cru do
botocore que chegava ao usuário como 500 num MinIO recém-subido.

### 2.2 Por que `upload_path` e não `save_path`

`save_path` **gera** a chave (`{workspace}/{uuid}-{nome}`) — certo para arquivo novo. Export e
condicionamento derivam a chave do asset de origem
(`{workspace}/exports/{asset}-{qualidade}.mp4`), e ela precisa permanecer estável porque é a
que já foi escrita na linha `Asset`. Gerar um UUID ali órfão a chave registrada.

### 2.3 Cliente sob demanda

```python
@property
def client(self):
    if self._client is None:
        self._client = boto3.client(...)
    return self._client
```

Importar `app.storage` não resolve mais credenciais nem região. Com setter, então
`storage.client = FakeS3()` funciona em teste — foi isso que permitiu cobrir o ramo S3.

### 2.4 Preservado sem alteração

`save`, `save_path`, `signed_url` e `local_path` mantêm assinatura e comportamento idênticos.
A única mudança em `signed_url` é usar a constante `PRESIGNED_TTL_SECONDS` em vez do literal
`3600` — mesmo valor.

---

## 3. Não-vacuidade

Remover o guard de *path traversal* (voltar `local_path` a devolver o caminho sem checar):

```
7 failed, 663 passed
FAILED test_traversal_keys_are_refused[../etc/passwd]
FAILED test_traversal_keys_are_refused[/etc/passwd]
FAILED test_upload_path_refuses_a_traversal_key
...
```

Restaurado, `670 passed` na ocasião. O controle de segurança agora tem garantia executável.

---

## 4. Verificações literais

| Verificação | Antes | **Depois** |
| --- | --- | --- |
| `storage.py` cobertura | 61% | **100%** |
| `pytest backend/tests -q` | 633 | **692 passed** |
| 22 testes originais | 22 | **22** |
| `test_core_independence.py` | 17 | **17** |
| Rotas `/api/v1` · core · WS | 54 · 27 · 2 | **54 · 27 · 2** |
| Cobertura total `backend/app` | 86% | **87%** |
| `npm run build` | ✓ | **✓** |
| Arquivos deletados desde `3708784` | 0 | **0** |
| Recusas 501 por storage | 4 | **0** |

`backend/tests/test_storage.py`: **37 testes**, com um cliente S3 falso em memória que grava
as chamadas — as asserções são sobre o que foi pedido ao S3, não só sobre o valor devolvido.

---

## 5. O que **não** foi verificado, dito explicitamente

Nada aqui foi fingido.

- **As rotas de condicionamento e export não foram executadas de ponta a ponta.** Pillow não
  está instalado (`ModuleNotFoundError: No module named 'PIL'`) e o FFmpeg não está no PATH
  (`media.available == False`, `binary: None`). Ambas respondem 503 **antes** de chegar ao
  storage neste sandbox. O religamento foi verificado estruturalmente (as strings de recusa
  sumiram, `storage.download` aparece nos dois pontos, a suíte continua verde), não por
  execução.
- **Nenhum MinIO real foi usado.** O ramo S3 foi exercitado contra um cliente falso. A
  assinatura das chamadas boto3 (`download_file(Bucket=, Key=, Filename=)`,
  `head_object`, `delete_object`, `create_bucket`) segue o SDK, mas o comportamento contra um
  servidor MinIO de verdade não foi observado aqui.
- **C8 permanece:** `minio` continua dependência morta em `requirements.txt`. Não foi
  removido — remover dependência não é aditivo, e a decisão é do mantenedor.

---

## 6. Arquivos

| Arquivo | Mudança |
| --- | --- |
| `backend/app/storage.py` | reescrito aditivamente — 108 stmts, 100% de cobertura |
| `backend/app/queue.py` | 2 recusas → `storage.download` |
| `backend/app/main.py` | 2 recusas → `storage.download` / `upload_path` |
| `backend/tests/test_storage.py` | **novo** — 37 testes |
| `CHANGELOG.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `README.md`, `backend/README.md` | atualizados |

Nenhum arquivo deletado.
