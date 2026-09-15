'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  addPersonaImage,
  Asset,
  createPersona,
  deletePersonaProfile,
  listAssets,
  listPersonaProfiles,
  PersonaProfile,
  updatePersonaProfile,
} from '../../../lib/api';
import { getAuthToken } from '../../../lib/memory/project_memory';
import {
  ArrowLeft,
  Eye,
  Image as ImageIcon,
  Plus,
  Save,
  Shirt,
  Sparkles,
  Trash2,
  UserRound,
} from 'lucide-react';

/**
 * PR003 — Persona Memory Engine screen (`/studio/personas`).
 *
 * The persistent persona profiles: list, create, edit (identity, wardrobe,
 * default style, LoRA), attach reference images from the asset library and
 * delete. Everything is tenant-scoped by the backend (404 for foreign ids);
 * this screen only renders what the API returns and shows its errors.
 *
 * Creation is two honest steps: `POST /api/v1/personas` (the original
 * training-flow contract, now persisting the row) followed by a
 * `PATCH` when the editor saves the extra profile fields — the same two
 * calls the backend exposes, no hidden writes.
 */

type FormState = {
  name: string;
  age: string;
  height: string;
  body_type: string;
  skin_tone: string;
  hair: string;
  beard: string;
  eyes: string;
  voice: string;
  default_style: string;
  lora_id: string;
};

const EMPTY_FORM: FormState = {
  name: '',
  age: '',
  height: '',
  body_type: '',
  skin_tone: '',
  hair: '',
  beard: '',
  eyes: '',
  voice: '',
  default_style: 'cinematic realism',
  lora_id: '',
};

const IMAGE_TYPES = ['face', 'body', 'style'] as const;

function fromProfile(profile: PersonaProfile): FormState {
  return {
    name: profile.name,
    age: String(profile.age || ''),
    height: String(profile.height || ''),
    body_type: profile.body_type,
    skin_tone: profile.skin_tone,
    hair: profile.hair,
    beard: profile.beard,
    eyes: profile.eyes,
    voice: profile.voice,
    default_style: profile.default_style,
    lora_id: profile.lora_id ?? '',
  };
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label>
      {label}
      {children}
    </label>
  );
}

function inputProps(value: string, onChange: (value: string) => void, placeholder = '') {
  return { value, onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value), placeholder };
}

function slugPreview(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 140) || 'persona';
}

function formatNotes(notes: Record<string, unknown>) {
  const changed = notes?.changed;
  if (changed && typeof changed === 'object') {
    return `alterou ${Object.keys(changed as object).join(', ')}`;
  }
  if (notes?.created) return 'criação';
  return 'histórico';
}

export default function PersonaProfilesPage() {
  const router = useRouter();
  const [profiles, setProfiles] = useState<PersonaProfile[] | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [wardrobe, setWardrobe] = useState<{ name: string; category: string; metadata: Record<string, unknown> }[]>([]);
  const [wardrobeDraft, setWardrobeDraft] = useState({ name: '', category: '' });
  const [attachType, setAttachType] = useState<(typeof IMAGE_TYPES)[number]>('face');
  const [attachPick, setAttachPick] = useState('');
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = useMemo(() => profiles?.find((profile) => profile.id === selectedId) ?? null, [profiles, selectedId]);
  const imageAssets = useMemo(() => assets.filter((asset) => asset.kind === 'image'), [assets]);
  const attachedIds = useMemo(() => new Set(selected?.images.map((image) => image.asset_id) ?? []), [selected]);

  const refresh = useCallback(async () => {
    const [profileResult, assetResult] = await Promise.all([listPersonaProfiles(), listAssets()]);
    if (profileResult.remote) setProfiles(profileResult.data);
    else if (profileResult.status === 401) setProfiles([]);
    if (assetResult.remote) setAssets(assetResult.data);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setField = (key: keyof FormState) => (value: string) => setForm((state) => ({ ...state, [key]: value }));

  const startEdit = (profile: PersonaProfile) => {
    setForm(fromProfile(profile));
    setWardrobe(profile.wardrobe.map((item) => ({ name: item.name, category: item.category, metadata: item.metadata })));
    setSelectedId(profile.id);
    setCreating(false);
    setMessage(null);
  };

  const startCreate = () => {
    setForm(EMPTY_FORM);
    setWardrobe([]);
    setSelectedId(null);
    setCreating(true);
    setMessage(null);
  };

  const closeEditor = () => {
    setCreating(false);
    setSelectedId(null);
    setMessage(null);
  };

  /** Step 1: the original (now persistent) creation endpoint. */
  const create = async () => {
    setBusy(true);
    setMessage(null);
    const created = await createPersona({
      name: form.name,
      age: Number(form.age) || 0,
      height_m: Number(form.height) || 1.7,
      appearance: form.body_type,
      eye_color: form.eyes,
      beard: form.beard,
      hair: form.hair,
      style: form.default_style,
    });
    if (created.remote) {
      const newId = String(created.data.id);
      await refresh();
      const profile = (await listPersonaProfiles()).data.find((item) => item.id === newId);
      setForm({ ...fromProfile(profile ?? ({} as PersonaProfile)), skin_tone: form.skin_tone, voice: form.voice });
      setWardrobe([]);
      setSelectedId(newId);
      setCreating(false);
      setMessage({
        kind: 'ok',
        text: `Persona “${form.name}” persistida no PostgreSQL (revisão 1). Salve o perfil para gravar tom de pele, voz e guarda-roupa.`,
      });
    } else {
      setMessage({ kind: 'error', text: created.error ?? 'Falha ao criar a persona.' });
    }
    setBusy(false);
  };

  /** Step 2 (and every edit after): the PATCH with the full profile. */
  const save = async () => {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    const payload: Record<string, unknown> = {
      name: form.name,
      age: Number(form.age) || 0,
      height: Number(form.height) || 1.7,
      body_type: form.body_type,
      skin_tone: form.skin_tone,
      hair: form.hair,
      beard: form.beard,
      eyes: form.eyes,
      voice: form.voice,
      default_style: form.default_style,
      lora_id: form.lora_id || null,
      wardrobe,
    };
    const result = await updatePersonaProfile(selected.id, payload);
    if (result.remote) {
      await refresh();
      setMessage({
        kind: 'ok',
        text: result.data.revision > selected.revision
          ? `Identidade atualizada — revisão ${result.data.revision} registrada no histórico.`
          : 'Perfil atualizado (sem mudança de identidade).',
      });
    } else {
      setMessage({ kind: 'error', text: result.error ?? 'Falha ao salvar.' });
    }
    setBusy(false);
  };

  const remove = async (profile: PersonaProfile) => {
    if (!window.confirm(`Excluir a persona “${profile.name}”? Assets referenciados e histórico de treino permanecem.`)) return;
    setBusy(true);
    const result = await deletePersonaProfile(profile.id);
    if (result.remote || result.status === 204) {
      if (selectedId === profile.id) closeEditor();
      await refresh();
      setMessage({ kind: 'ok', text: `Persona “${profile.name}” excluída.` });
    } else {
      setMessage({ kind: 'error', text: result.error ?? 'Falha ao excluir.' });
    }
    setBusy(false);
  };

  const attachImage = async () => {
    if (!selected || !attachPick) return;
    const result = await addPersonaImage(selected.id, { asset_id: attachPick, image_type: attachType });
    if (result.remote) {
      setAttachPick('');
      await refresh();
      setMessage({ kind: 'ok', text: `Imagem anexada como “${attachType}”.` });
    } else {
      setMessage({ kind: 'error', text: result.error ?? 'Falha ao anexar imagem.' });
    }
  };

  // PR004.1: the session check goes through the Memory Adapter's accessor —
  // components never name the raw token key or touch localStorage directly.
  const hasToken = getAuthToken() !== null;
  const showEditor = creating || selected !== null;

  return (
    <main className="app-shell">
      <aside className="sidebar collapsed" />
      <div className="main-area">
        <div className="content">
          <div className="page-header">
            <div>
              <div className="eyebrow">
                <UserRound size={12} /> PERSONA MEMORY ENGINE — PR003
              </div>
              <h1>Persona profiles</h1>
              <p>
                Perfis persistentes em PostgreSQL — identidade, guarda-roupa, estilo padrão, LoRA e imagens de
                referência. Cada mudança de identidade appende uma revisão imutável.
              </p>
            </div>
            <div className="header-actions">
              <button className="secondary-button" onClick={() => router.push('/')}>
                <ArrowLeft size={13} /> Voltar ao estúdio
              </button>
              {!showEditor && (
                <button className="primary-button" onClick={startCreate}>
                  <Plus size={13} /> Nova persona
                </button>
              )}
            </div>
          </div>

          {!hasToken && (
            <div className="notice notice-error">
              <Eye size={13} />
              <span>
                Estas rotas exigem identidade: <strong>entre no estúdio</strong> (login na página inicial) e volte
                para gerenciar suas personas.
              </span>
            </div>
          )}

          {message && (
            <div className={`notice ${message.kind === 'error' ? 'notice-error' : ''}`}>
              {message.kind === 'error' ? <Trash2 size={13} /> : <Sparkles size={13} />}
              <span>{message.text}</span>
            </div>
          )}

          {showEditor && (
            <div className="persona-layout" style={{ marginBottom: 26 }}>
              <div className="control-panel">
                <div className="panel-heading">
                  {creating ? 'Nova persona' : `Editar — ${selected?.name}`}
                  <button className="magic-button" onClick={closeEditor}>
                    <ArrowLeft size={11} /> fechar
                  </button>
                </div>
                <div className="form-row">
                  <Field label="Nome">
                    <input {...inputProps(form.name, setField('name'), 'Rafaela Costa')} />
                  </Field>
                  <Field label="Slug (gerado)">
                    <input disabled value={slugPreview(form.name)} />
                  </Field>
                </div>
                <div className="form-row">
                  <Field label="Idade">
                    <input {...inputProps(form.age, setField('age'), '34')} />
                  </Field>
                  <Field label="Altura (m)">
                    <input {...inputProps(form.height, setField('height'), '1.72')} />
                  </Field>
                  <Field label="Corpo">
                    <input {...inputProps(form.body_type, setField('body_type'), 'Slender / Athletic…')} />
                  </Field>
                </div>
                <div className="form-row">
                  <Field label="Tom de pele">
                    <input {...inputProps(form.skin_tone, setField('skin_tone'), 'warm olive')} />
                  </Field>
                  <Field label="Cabelo">
                    <input {...inputProps(form.hair, setField('hair'), 'wavy dark')} />
                  </Field>
                  <Field label="Barba">
                    <input {...inputProps(form.beard, setField('beard'), 'light stubble')} />
                  </Field>
                </div>
                <div className="form-row">
                  <Field label="Olhos">
                    <input {...inputProps(form.eyes, setField('eyes'), 'Amber')} />
                  </Field>
                  <Field label="Voz">
                    <input {...inputProps(form.voice, setField('voice'), 'low, calm')} />
                  </Field>
                  <Field label="Estilo padrão">
                    <input {...inputProps(form.default_style, setField('default_style'), 'cinematic realism')} />
                  </Field>
                </div>
                <Field label="LoRA treinado (asset id — vazio = nenhum)">
                  <input {...inputProps(form.lora_id, setField('lora_id'), 'id do asset .safetensors')} />
                </Field>

                <div style={{ borderTop: '1px solid #28272a', margin: '18px -18px 0', padding: '14px 18px 0' }}>
                  <div className="panel-heading">
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Shirt size={12} /> Guarda-roupa ({wardrobe.length})
                    </span>
                  </div>
                  {wardrobe.map((item, index) => (
                    <div className="detail-row" key={`${item.name}-${index}`}>
                      <span>
                        {item.name} <span className="muted">— {item.category || 'geral'}</span>
                      </span>
                      <button
                        className="text-button"
                        onClick={() => setWardrobe((items) => items.filter((_, i) => i !== index))}
                      >
                        <Trash2 size={11} /> remover
                      </button>
                    </div>
                  ))}
                  <div className="form-row" style={{ alignItems: 'flex-end' }}>
                    <Field label="Nova peça">
                      <input
                        {...inputProps(wardrobeDraft.name, (value) => setWardrobeDraft((state) => ({ ...state, name: value })), 'trench coat')}
                      />
                    </Field>
                    <Field label="Categoria">
                      <input
                        {...inputProps(wardrobeDraft.category, (value) => setWardrobeDraft((state) => ({ ...state, category: value })), 'coat / dress…')}
                      />
                    </Field>
                    <button
                      className="secondary-button"
                      onClick={() => {
                        if (!wardrobeDraft.name.trim()) return;
                        setWardrobe((items) => [
                          ...items,
                          { name: wardrobeDraft.name.trim(), category: wardrobeDraft.category.trim(), metadata: {} },
                        ]);
                        setWardrobeDraft({ name: '', category: '' });
                      }}
                    >
                      <Plus size={12} /> Adicionar
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
                  {creating ? (
                    <button className="primary-button full" disabled={busy || !form.name.trim()} onClick={create}>
                      {busy ? 'Criando…' : 'Criar persona'}
                    </button>
                  ) : (
                    <button className="primary-button full" disabled={busy} onClick={save}>
                      {busy ? 'Salvando…' : 'Salvar perfil'}
                    </button>
                  )}
                </div>
              </div>

              <div className="training-panel">
                <div className="panel-heading">
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ImageIcon size={12} /> Imagens de referência
                  </span>
                </div>
                {!selected ? (
                  <p className="muted" style={{ fontSize: 10, margin: 0 }}>
                    Crie a persona para anexar imagens do acervo. A persona só referencia assets existentes — o
                    upload continua na tela de assets.
                  </p>
                ) : (
                  <>
                    {selected.images.length === 0 && (
                      <p className="muted" style={{ fontSize: 10, margin: '0 0 12px' }}>
                        Nenhuma imagem anexada ainda.
                      </p>
                    )}
                    {selected.images.map((image) => (
                      <div className="detail-row" key={image.id}>
                        <span>
                          {image.name ?? image.asset_id.slice(0, 8)}{' '}
                          <span className="muted">— {image.image_type} · #{image.order_index}</span>
                        </span>
                        {image.url ? (
                          <a className="text-button" href={image.url} target="_blank" rel="noreferrer">
                            <Eye size={11} /> ver
                          </a>
                        ) : (
                          <span className="muted" style={{ fontSize: 9 }}>
                            asset removido
                          </span>
                        )}
                      </div>
                    ))}
                    <div className="form-row" style={{ marginTop: 14, alignItems: 'flex-end' }}>
                      <Field label="Tipo">
                        <select value={attachType} onChange={(e) => setAttachType(e.target.value as (typeof IMAGE_TYPES)[number])} style={{ background: "#1a191c", border: "1px solid #2b292e", borderRadius: 7, padding: "8px 10px", fontSize: 11 }}>
                          {IMAGE_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Asset do acervo">
                        <select value={attachPick} onChange={(e) => setAttachPick(e.target.value)} style={{ background: "#1a191c", border: "1px solid #2b292e", borderRadius: 7, padding: "8px 10px", fontSize: 11 }}>
                          <option value="">selecionar…</option>
                          {imageAssets
                            .filter((asset) => !attachedIds.has(asset.id))
                            .map((asset) => (
                              <option key={asset.id} value={asset.id}>
                                {asset.name}
                              </option>
                            ))}
                        </select>
                      </Field>
                      <button className="secondary-button" disabled={!attachPick} onClick={attachImage}>
                        <Plus size={12} />
                      </button>
                    </div>
                  </>
                )}

                {selected && (
                  <>
                    <div style={{ borderTop: '1px solid #28272a', margin: '18px -18px 0', padding: '14px 18px 0' }}>
                      <div className="panel-heading">
                        <span>Histórico — revisão {selected.revision}</span>
                      </div>
                      {[...selected.revisions].reverse().map((revision) => (
                        <div className="detail-row" key={revision.id}>
                          <span>
                            #{revision.revision}
                            <span className="muted"> · {formatNotes(revision.notes)}</span>
                          </span>
                          <span className="muted" style={{ fontSize: 9 }}>
                            {new Date(revision.created_at).toLocaleDateString('pt-BR')}
                          </span>
                        </div>
                      ))}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 18 }}>
                      <button className="secondary-button" disabled={busy} onClick={() => remove(selected)}>
                        <Trash2 size={12} /> Excluir persona
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          <div className="section-row" style={{ marginBottom: 12 }}>
            <div>
              <h2 className="section-title">Perfis do workspace</h2>
              <p className="section-subtitle">
                {profiles === null
                  ? 'Carregando…'
                  : `${profiles.length} persona${profiles.length === 1 ? '' : 's'} persistida${profiles.length === 1 ? '' : 's'}`}
              </p>
            </div>
          </div>

          {profiles === null ? (
            <div className="empty-library">
              <UserRound size={26} />
              <h3>Consultando o PostgreSQL…</h3>
              <p>tabelas personas / persona_images / persona_wardrobe / persona_identity_revision</p>
            </div>
          ) : profiles.length === 0 ? (
            <div className="empty-library">
              <UserRound size={26} />
              <h3>Nenhuma persona persistida</h3>
              <p>
                {hasToken
                  ? 'Crie a primeira persona — ela vira linhas em 4 tabelas (Alembic 0002).'
                  : 'Entre no estúdio para desbloquear as rotas autenticadas.'}
              </p>
            </div>
          ) : (
            <div className="project-grid">
              {profiles.map((profile) => (
                <div className="persona-card" key={profile.id}>
                  <div className="persona-cover">
                    <div className="persona-portrait">
                      <UserRound size={44} />
                    </div>
                    {profile.lora_id ? (
                      <span className="trained-badge">LoRA ativo</span>
                    ) : (
                      <span className="trained-badge" style={{ background: '#241f31', color: '#b39aff' }}>
                        sem LoRA
                      </span>
                    )}
                  </div>
                  <div className="persona-body">
                    <div>
                      <h2>{profile.name}</h2>
                      <p>
                        {profile.age} anos · {profile.height ? profile.height.toFixed(2) : '—'} m · {profile.eyes || '—'}
                      </p>
                    </div>
                    <button className="secondary-button" onClick={() => startEdit(profile)}>
                      <Save size={12} /> Editar
                    </button>
                    <div className="persona-tags">
                      {profile.body_type && <span>{profile.body_type}</span>}
                      {profile.hair && <span>{profile.hair}</span>}
                      {profile.default_style && <span>estilo: {profile.default_style}</span>}
                      <span>{profile.wardrobe.length} peça(s)</span>
                      <span>{profile.images.length} imagem(ns)</span>
                    </div>
                    <div className="persona-footer">
                      <span>
                        <Sparkles size={10} /> revisão {profile.revision}
                      </span>
                      <span>
                        {new Date(profile.updated_at).toLocaleDateString('pt-BR')} · {profile.slug}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
