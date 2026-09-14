# BROBOND AI STUDIO ROADMAP

Este documento é a fonte estratégica do produto. Toda nova feature deve ser classificada aqui antes de ser implementada.

## Status atual

A fundação visual, API, autenticação, jobs, storage, providers, prompt engine, storyboard, personas, LoRA contracts, conditioning e readiness operacional já estão estruturados. A execução de modelos reais depende de hardware GPU, pesos e providers instalados.

## v1.0 — Workspace local

- [x] Interface premium
- [x] Image Generation contract
- [x] Video Generation contract
- [x] Projects, Assets e upload
- [x] Auth JWT e workspace
- [x] Redis/Celery/WebSocket contracts
- [ ] Primeiro render GPU validado ponta a ponta

## v1.5 — Direção visual

- [x] Motion Control presets
- [x] Storyboard continuity
- [x] Prompt Engine
- [x] ControlNet/IP Adapter contracts
- [ ] Shot Library completa com 300+ presets
- [ ] Cinematic presets persistidos e editáveis

## v2.0 — BROBOND CORE

- [x] Persona LoRA contracts
- [x] Character memory foundation
- [x] Versioned LoRA assets
- [x] Knowledge Base persistente no PostgreSQL
- [x] Memory Resolver API inicial
- [ ] Memory Resolver em cada GenerationSpec
- [ ] Character Library completa
- [ ] Prompt Library classificada
- [ ] Continuidade entre episódios

## v3.0 — AI Director

- [ ] Conversa de direção: trailer, luxo, fashion film, documental
- [ ] Roteirista automático
- [ ] Diretor de câmera IA
- [ ] Ritmo, montagem, música e iluminação por intenção
- [ ] Voice Clone
- [ ] Lip Sync

## v4.0 — Escala

- [ ] Multi-agent collaboration real
- [ ] Multi-tenancy SaaS
- [ ] Cloud rendering e autoscaling
- [ ] Créditos, quotas e billing
- [ ] Mobile app
- [ ] Painel administrativo

## Regra de evolução

Toda nova solicitação deve informar: versão, módulo, impacto na memória, impacto nos providers, contrato de API, UX, testes e documentação. Features que não se encaixam em uma versão devem primeiro atualizar este arquivo.
