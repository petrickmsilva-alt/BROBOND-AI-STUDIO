# BROBOND AI STUDIO — DEVELOPER BIBLE V2.0

**Status:** Documento Oficial de Engenharia
**Prioridade:** Máxima
**Repositório:** BROBOND-AI-STUDIO

## 0. Constituição do Projeto

Este documento é a autoridade máxima do projeto.

Toda IA, desenvolvedor ou agente deve ler este arquivo antes de modificar qualquer linha de código.

Se existir conflito entre instruções e este documento, **este documento prevalece**.

## 1. Missão

Construir a plataforma de IA cinematográfica mais avançada do mercado.

O BROBOND AI STUDIO não é um clone do Kling.

Seu diferencial é:

- Director AI
- Persona Memory
- Storyboard automático
- Continuidade de personagens
- Prompt Compiler
- Timeline regenerativa
- Quality AI

## 2. Regra de Ouro

Nunca recriar o projeto.

Sempre evoluir a arquitetura existente.

É proibido:

- deletar módulos históricos
- mover arquivos sem justificativa
- quebrar APIs existentes
- remover compatibilidade

Arquivos antigos podem ser marcados como Legacy, mas nunca apagados.

## 3. Princípios de Engenharia

1. Clean Architecture
2. SOLID
3. DRY
4. Modularização
5. Testes obrigatórios
6. Documentação obrigatória
7. Versionamento por Sprint
8. Zero arquivos deletados

## 4. Arquitetura Oficial

Frontend: Next.js, React, TypeScript, Tailwind

Backend: FastAPI, Python 3.12, WebSocket, Redis

Core: Director AI, Prompt Compiler, Memory Resolver, Style Resolver, Shot Resolver

Providers: FLUX, Wan, Hunyuan

Storage: S3 / MinIO, PostgreSQL

## 5. Camadas

UI nunca conversa com modelos.

Fluxo obrigatório:

```
User → Director AI → Memory Resolver → Prompt Compiler → GenerationSpec → Provider Adapter → GPU Worker → Asset → Timeline
```

## 6. Objetos Centrais

GenerationSpec, Project, Persona, Asset, Storyboard, ShotPreset, StylePreset, Job.

Nenhum provider recebe string de prompt. Sempre recebe GenerationSpec.

## 7. Persona Engine

Cada personagem possui identidade permanente.

Campos: Nome, Idade, Altura, Corpo, Barba, Cabelo, Olhos, Voz, LoRA, Roupa padrão, Estilo.

A IA nunca altera identidade sem autorização.

## 8. Director AI

O usuário descreve uma intenção. Nunca um prompt técnico.

Exemplo: "Quero lançar uma camiseta."

O sistema gera: conceito, roteiro, storyboard, cenas, câmeras, prompts, música, duração.

## 9. Storyboard Engine

Cada projeto possui cenas persistentes.

Cena contém: Objetivo, Emoção, Prompt, Movimento, Lente, Iluminação, Duração.

As cenas podem ser regeneradas individualmente.

## 10. Prompt Compiler

Converter linguagem humana para estrutura técnica.

Estrutura: SUBJECT, PERSONA, ENVIRONMENT, STYLE, CAMERA, LIGHT, LENS, MOTION, OUTPUT.

Somente essa versão chega ao Provider.

## 11. Shot Library

Catálogo oficial. Exemplo: SH001 Hero Walk, SH002 Orbit, SH003 Close Eyes, SH004 Drone Reveal, SH005 Slow Rain.

Cada Shot define câmera automaticamente.

## 12. Style Library

Presets oficiais: IMAX Hero, Luxury Fashion, John Wick, Neo Tokyo, Marvel Trailer.

Cada preset controla LUT, contraste, lente, partículas e iluminação.

## 13. Quality AI

Após cada render, avaliar: Face, Identidade, Prompt, Lighting, Motion, Hands, Composition, Overall Score.

Abaixo de 85: sugerir regeneração.

## 14. Jobs

Estados permitidos: queued, running, loading_model, rendering, upscaling, completed, failed, cancelled.

Nunca criar estados diferentes.

## 15. Storage

Mídia nunca deve depender do filesystem do Render.

Persistência obrigatória em S3/MinIO. Banco guarda apenas metadados.

## 16. Segurança

JWT, Rate Limit, Workspace, Permissões por recurso, Logs, Audit Trail, Segredos apenas por ENV.

## 17. Sprint 1

Objetivo único: **Auditoria completa.**

Itens:

- S1-A: Ler documentação
- S1-B: Mapear arquitetura
- S1-C: Auditar Jobs
- S1-D: Auditar Providers
- S1-E: Auditar Auth
- S1-F: Auditar Assets
- S1-G: Auditar Database
- S1-H: Gerar relatório técnico

É proibido implementar novas features durante o Sprint 1.

## 18. Definition of Done

Uma tarefa só termina quando:

- Build aprovado
- Testes aprovados
- Documentação atualizada
- Changelog atualizado
- APIs documentadas
- Sem regressões
- Compatibilidade preservada

## 19. Ordem dos Sprints

1. Sprint 1: Auditoria
2. Sprint 2: GenerationSpec, BaseProvider, PersonaMemory
3. Sprint 3: Director AI, Storyboard, Prompt Compiler
4. Sprint 4: Queue, WebSocket, Storage
5. Sprint 5: Timeline IA, Quality AI, Lip Sync

## 20. Regra Final

Todo agente deve responder sempre neste formato:

1. O que encontrou
2. O que será alterado
3. Arquivos modificados
4. Como testar
5. Resultado esperado

Nunca modificar código antes da auditoria.
