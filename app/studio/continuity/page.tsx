'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Car,
  CheckCircle2,
  Clapperboard,
  Fingerprint,
  ListVideo,
  LockKeyhole,
  MapPin,
  Mic,
  Plus,
  RefreshCcw,
  Shirt,
  UserRound,
  XCircle,
} from 'lucide-react';
import type {
  ContinuityContextResult,
  ContinuityEpisode,
  ContinuityIdentity,
  ContinuityLocation,
  ContinuityVehicle,
  ContinuityVoice,
  ContinuityWardrobe,
} from '../../../lib/api';
import { NetworkErrorType } from '../../../lib/network/request';
import { failureMessage } from '../../../lib/network/status';
import {
  createContinuityEpisode,
  getContinuityIdentity,
  getContinuityLocation,
  getContinuityVehicle,
  getContinuityVoice,
  getContinuityWardrobe,
  listContinuityEpisodes,
  listPersonaProfiles,
  lockContinuityIdentity,
  lockContinuityLocation,
  lockContinuityVehicle,
  lockContinuityVoice,
  lockContinuityWardrobe,
  resolveContinuity,
} from '../../../lib/api';

type FieldSpec = { key: string; label: string; placeholder: string };

const IDENTITY_FIELDS: FieldSpec[] = [
  { key: 'face', label: 'Rosto', placeholder: 'ex. oval face' },
  { key: 'hair', label: 'Cabelo', placeholder: 'ex. tied back' },
  { key: 'beard', label: 'Barba', placeholder: 'ex. short beard' },
  { key: 'body', label: 'Corpo', placeholder: 'ex. athletic build' },
  { key: 'skin', label: 'Pele', placeholder: 'ex. warm brown' },
  { key: 'age_appearance', label: 'Idade aparente', placeholder: 'ex. 50 years old' },
];

const WARDROBE_FIELDS: FieldSpec[] = [
  { key: 'outfit', label: 'Roupa *', placeholder: 'ex. black blazer' },
  { key: 'accessories', label: 'Acessórios', placeholder: 'ex. silver chain' },
  { key: 'colors', label: 'Cores', placeholder: 'ex. black and gold' },
  { key: 'shoes', label: 'Sapatos', placeholder: 'ex. chelsea boots' },
  { key: 'watch', label: 'Relógio', placeholder: 'ex. steel chronograph' },
];

const LOCATION_FIELDS: FieldSpec[] = [
  { key: 'showroom', label: 'Showroom', placeholder: 'ex. BROBOND Flagship' },
  { key: 'studio', label: 'Estúdio', placeholder: 'ex. Studio B' },
  { key: 'street', label: 'Rua', placeholder: 'ex. Rua Oscar Freire' },
  { key: 'city', label: 'Cidade', placeholder: 'ex. São Paulo' },
  { key: 'base_lighting', label: 'Iluminação base', placeholder: 'ex. warm tungsten' },
];

const VEHICLE_FIELDS: FieldSpec[] = [
  { key: 'vehicle', label: 'Veículo *', placeholder: 'ex. RAM 1500' },
  { key: 'color', label: 'Cor *', placeholder: 'ex. branco pérola' },
  { key: 'plate', label: 'Placa (opcional)', placeholder: 'ex. ABC1D23' },
  { key: 'wheels', label: 'Rodas', placeholder: 'ex. 22 graphite' },
  { key: 'finish', label: 'Acabamento', placeholder: 'ex. matte PPF' },
];

const VOICE_FIELDS: FieldSpec[] = [
  { key: 'voice_profile', label: 'Perfil de voz *', placeholder: 'ex. petrick-low-warm' },
  { key: 'default_emotion', label: 'Emoção padrão', placeholder: 'ex. confident' },
  { key: 'speed', label: 'Velocidade', placeholder: 'ex. 1.0x' },
  { key: 'intensity', label: 'Intensidade', placeholder: 'ex. high' },
];

type LockData =
  | ContinuityIdentity
  | ContinuityWardrobe
  | ContinuityLocation
  | ContinuityVehicle
  | ContinuityVoice;

function emptyForm(fields: FieldSpec[]): Record<string, string> {
  return Object.fromEntries(fields.map(field => [field.key, '']));
}

function formFromLock(fields: FieldSpec[], lock: LockData | null): Record<string, string> {
  const form = emptyForm(fields);
  if (!lock) return form;
  for (const field of fields) {
    const value = (lock as unknown as Record<string, unknown>)[field.key];
    if (typeof value === 'string') form[field.key] = value;
  }
  return form;
}

function describeError(result: { error?: string; errorType?: NetworkErrorType; status?: number }): string {
  if (result.status === 401) return 'Entre com sua conta — continuidade exige identidade.';
  return failureMessage(result, 'API offline — inicie o FastAPI para travar continuidade.');
}

function LockCard({
  title,
  subtitle,
  icon,
  fields,
  lock,
  loading,
  form,
  onForm,
  saving,
  message,
  onSave,
  scopeHint,
}: {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  fields: FieldSpec[];
  lock: LockData | null;
  loading: boolean;
  form: Record<string, string>;
  onForm: (key: string, value: string) => void;
  saving: boolean;
  message: { kind: 'ok' | 'error'; text: string } | null;
  onSave: () => void;
  scopeHint: string;
}) {
  return (
    <section className="continuity-card" aria-label={title}>
      <header>
        <span className="continuity-card-icon">{icon}</span>
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        {lock ? (
          <span className="continuity-locked"><LockKeyhole size={12} /> travado</span>
        ) : (
          <span className="continuity-unlocked">livre</span>
        )}
      </header>

      {loading ? (
        <p className="continuity-muted">Carregando…</p>
      ) : lock ? (
        <div className="continuity-lock-view">
          <dl>
            {fields.map(field => {
              const value = (lock as unknown as Record<string, unknown>)[field.key];
              return (
                <div key={field.key}>
                  <dt>{field.label.replace(' *', '')}</dt>
                  <dd>{typeof value === 'string' && value ? value : '—'}</dd>
                </div>
              );
            })}
          </dl>
          <p className="continuity-fingerprint" title="Fingerprint visual do lock">
            <Fingerprint size={13} /> {lock.fingerprint} · v{lock.version} · {scopeHint}
          </p>
        </div>
      ) : (
        <p className="continuity-muted">Nada travado neste escopo — preencha e salve.</p>
      )}

      <div className="continuity-form">
        {fields.map(field => (
          <label key={field.key}>
            {field.label}
            <input
              value={form[field.key] ?? ''}
              onChange={event => onForm(field.key, event.target.value)}
              placeholder={field.placeholder}
            />
          </label>
        ))}
      </div>
      {message && (
        <p className={message.kind === 'ok' ? 'continuity-ok' : 'continuity-form-error'}>{message.text}</p>
      )}
      <button type="button" className="primary-button" onClick={onSave} disabled={saving}>
        <LockKeyhole size={14} /> {saving ? 'Travando…' : lock ? 'Atualizar lock' : 'Travar'}
      </button>
    </section>
  );
}

export default function ContinuityPage() {
  const [personaId, setPersonaId] = useState('CHAR_PETRICK');
  const [campaignId, setCampaignId] = useState('legacy');
  const [episode, setEpisode] = useState('1');
  const [saveScope, setSaveScope] = useState<'default' | 'episode'>('default');
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const [identity, setIdentity] = useState<ContinuityIdentity | null>(null);
  const [wardrobe, setWardrobe] = useState<ContinuityWardrobe | null>(null);
  const [location, setLocation] = useState<ContinuityLocation | null>(null);
  const [vehicle, setVehicle] = useState<ContinuityVehicle | null>(null);
  const [voice, setVoice] = useState<ContinuityVoice | null>(null);

  const [identityForm, setIdentityForm] = useState(emptyForm(IDENTITY_FIELDS));
  const [wardrobeForm, setWardrobeForm] = useState(emptyForm(WARDROBE_FIELDS));
  const [locationForm, setLocationForm] = useState(emptyForm(LOCATION_FIELDS));
  const [vehicleForm, setVehicleForm] = useState(emptyForm(VEHICLE_FIELDS));
  const [voiceForm, setVoiceForm] = useState(emptyForm(VOICE_FIELDS));

  const [saving, setSaving] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, { kind: 'ok' | 'error'; text: string } | null>>({});

  const [context, setContext] = useState<ContinuityContextResult | null>(null);
  const [resolving, setResolving] = useState(false);
  const [contextError, setContextError] = useState<string | undefined>();

  const [episodes, setEpisodes] = useState<ContinuityEpisode[]>([]);
  const [episodesError, setEpisodesError] = useState<string | undefined>();
  const [episodeTitle, setEpisodeTitle] = useState('');
  const [episodeNotes, setEpisodeNotes] = useState('');
  const [creating, setCreating] = useState(false);
  const [episodeMessage, setEpisodeMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const episodeNumber = Number.parseInt(episode, 10);

  const scopedEpisode = (): number | undefined =>
    saveScope === 'episode' && Number.isInteger(episodeNumber) && episodeNumber >= 1 ? episodeNumber : undefined;

  const load = useCallback(async () => {
    const persona = personaId.trim();
    const campaign = campaignId.trim() || 'default';
    const ep = Number.isInteger(episodeNumber) && episodeNumber >= 1 ? episodeNumber : 1;
    if (!persona) {
      setError('Informe o persona_id para carregar a continuidade.');
      return;
    }
    setLoading(true);
    setError(undefined);
    const [identityResult, wardrobeResult, locationResult, vehicleResult, voiceResult, episodesResult] =
      await Promise.all([
        getContinuityIdentity(persona),
        getContinuityWardrobe({ persona_id: persona, campaign_id: campaign, episode: ep }),
        getContinuityLocation({ persona_id: persona, campaign_id: campaign, episode: ep }),
        getContinuityVehicle({ persona_id: persona, campaign_id: campaign, episode: ep }),
        getContinuityVoice(persona),
        listContinuityEpisodes({ persona_id: persona, campaign_id: campaign }),
      ]);
    const fatal = [identityResult, wardrobeResult, locationResult, vehicleResult, voiceResult].find(
      result => !result.remote && result.status !== 404,
    );
    if (fatal) {
      setError(describeError(fatal));
      setLoading(false);
      return;
    }
    const identityLock = identityResult.remote ? identityResult.data : null;
    const wardrobeLock = wardrobeResult.remote ? wardrobeResult.data : null;
    const locationLock = locationResult.remote ? locationResult.data : null;
    const vehicleLock = vehicleResult.remote ? vehicleResult.data : null;
    const voiceLock = voiceResult.remote ? voiceResult.data : null;
    setIdentity(identityLock);
    setWardrobe(wardrobeLock);
    setLocation(locationLock);
    setVehicle(vehicleLock);
    setVoice(voiceLock);
    setIdentityForm(formFromLock(IDENTITY_FIELDS, identityLock));
    setWardrobeForm(formFromLock(WARDROBE_FIELDS, wardrobeLock));
    setLocationForm(formFromLock(LOCATION_FIELDS, locationLock));
    setVehicleForm(formFromLock(VEHICLE_FIELDS, vehicleLock));
    setVoiceForm(formFromLock(VOICE_FIELDS, voiceLock));
    if (episodesResult.remote) {
      setEpisodes(episodesResult.data);
      setEpisodesError(undefined);
    } else {
      setEpisodes([]);
      setEpisodesError(describeError(episodesResult));
    }
    setLoading(false);
  }, [personaId, campaignId, episodeNumber]);

  const resolve = useCallback(async () => {
    const persona = personaId.trim();
    const campaign = campaignId.trim() || 'default';
    const ep = Number.isInteger(episodeNumber) && episodeNumber >= 1 ? episodeNumber : 1;
    if (!persona) {
      setContextError('Informe o persona_id para resolver o contexto.');
      return;
    }
    setResolving(true);
    setContextError(undefined);
    const result = await resolveContinuity({ persona_id: persona, campaign_id: campaign, episode: ep });
    if (result.remote) setContext(result.data);
    else {
      setContext(null);
      setContextError(describeError(result));
    }
    setResolving(false);
  }, [personaId, campaignId, episodeNumber]);

  useEffect(() => {
    listPersonaProfiles().then(result => {
      if (result.remote) setSuggestions(result.data.map(profile => profile.id));
    });
  }, []);

  const save = async (
    key: string,
    call: () => Promise<{ remote: boolean; data: LockData; error?: string; errorType?: NetworkErrorType; status?: number }>,
    apply: (lock: LockData) => void,
  ) => {
    setSaving(key);
    setMessages(state => ({ ...state, [key]: null }));
    const result = await call();
    if (result.remote) {
      apply(result.data);
      setMessages(state => ({ ...state, [key]: { kind: 'ok', text: `Travado — fingerprint ${result.data.fingerprint}.` } }));
    } else {
      setMessages(state => ({ ...state, [key]: { kind: 'error', text: describeError(result) } }));
    }
    setSaving(null);
  };

  const setFormValue = (setter: React.Dispatch<React.SetStateAction<Record<string, string>>>) =>
    (key: string, value: string) => setter(state => ({ ...state, [key]: value }));

  const createEpisode = async () => {
    const persona = personaId.trim();
    const campaign = campaignId.trim() || 'default';
    if (!persona) {
      setEpisodeMessage({ kind: 'error', text: 'Informe o persona_id para criar o episódio.' });
      return;
    }
    setCreating(true);
    setEpisodeMessage(null);
    const result = await createContinuityEpisode({
      persona_id: persona,
      campaign_id: campaign,
      title: episodeTitle.trim(),
      notes: episodeNotes.trim(),
    });
    if (result.remote) {
      setEpisodeMessage({ kind: 'ok', text: `Episódio ${result.data.episode} congelado com a continuidade atual.` });
      setEpisodeTitle('');
      setEpisodeNotes('');
      const refreshed = await listContinuityEpisodes({ persona_id: persona, campaign_id: campaign });
      if (refreshed.remote) setEpisodes(refreshed.data);
    } else {
      setEpisodeMessage({ kind: 'error', text: describeError(result) });
    }
    setCreating(false);
  };

  const scopeHintFor = (lock: { source_episode?: number | null } | null, global: boolean): string => {
    if (global) return 'persona-global';
    if (!lock) return '—';
    return lock.source_episode === null || lock.source_episode === undefined
      ? 'padrão da campanha'
      : `episódio ${lock.source_episode}`;
  };

  return <main className="continuity-page">
    <section className="continuity-hero">
      <div>
        <div className="eyebrow"><Clapperboard size={13} /> V3.2 · CHARACTER CONTINUITY ENGINE</div>
        <h1>O mesmo personagem em qualquer episódio.</h1>
        <p>Identidade, figurino, locação, veículo e voz congelados por campanha — com override por
          episódio, fingerprint visual e histórico imutável. O resolver monta o contexto
          cinematográfico sem tocar no GenerationSpec.</p>
      </div>
      <div className="continuity-hero-actions">
        <button type="button" className="primary-button" onClick={load} disabled={loading}>
          <RefreshCcw size={15} /> {loading ? 'Carregando…' : 'Carregar'}
        </button>
      </div>
    </section>

    {error && <div className="continuity-error"><XCircle size={15} /> {error}</div>}

    <section className="continuity-scope" aria-label="Escopo">
      <label>
        Persona
        <input
          value={personaId}
          onChange={event => setPersonaId(event.target.value)}
          placeholder="CHAR_PETRICK"
          list="continuity-personas"
        />
        <datalist id="continuity-personas">
          {suggestions.map(id => <option key={id} value={id} />)}
        </datalist>
      </label>
      <label>
        Campanha
        <input
          value={campaignId}
          onChange={event => setCampaignId(event.target.value)}
          placeholder="legacy"
        />
      </label>
      <label className="continuity-episode-input">
        Episódio
        <input
          value={episode}
          onChange={event => setEpisode(event.target.value)}
          placeholder="1"
          inputMode="numeric"
        />
      </label>
      <label className="continuity-save-scope">
        Salvar roupa/local/veículo como
        <select value={saveScope} onChange={event => setSaveScope(event.target.value as 'default' | 'episode')}>
          <option value="default">Padrão da campanha</option>
          <option value="episode">Só este episódio</option>
        </select>
      </label>
      <button type="button" className="continuity-ghost" onClick={resolve} disabled={resolving}>
        <CheckCircle2 size={15} /> {resolving ? 'Resolvendo…' : 'Resolver contexto'}
      </button>
    </section>

    <section className="continuity-grid">
      <LockCard
        title="Personagem"
        subtitle="Identity Lock — rosto, cabelo, barba, corpo, pele, idade"
        icon={<UserRound size={16} />}
        fields={IDENTITY_FIELDS}
        lock={identity}
        loading={loading}
        form={identityForm}
        onForm={setFormValue(setIdentityForm)}
        saving={saving === 'identity'}
        message={messages.identity ?? null}
        onSave={() => save('identity',
          () => lockContinuityIdentity({ persona_id: personaId.trim(), ...identityForm }),
          lock => { setIdentity(lock as ContinuityIdentity); setIdentityForm(formFromLock(IDENTITY_FIELDS, lock)); })}
        scopeHint={scopeHintFor(null, true)}
      />
      <LockCard
        title="Roupa"
        subtitle="Wardrobe Lock — peça, acessórios, cores, sapatos, relógio"
        icon={<Shirt size={16} />}
        fields={WARDROBE_FIELDS}
        lock={wardrobe}
        loading={loading}
        form={wardrobeForm}
        onForm={setFormValue(setWardrobeForm)}
        saving={saving === 'wardrobe'}
        message={messages.wardrobe ?? null}
        onSave={() => save('wardrobe',
          () => lockContinuityWardrobe({
            persona_id: personaId.trim(),
            campaign_id: campaignId.trim() || 'default',
            episode: scopedEpisode(),
            ...wardrobeForm,
          }),
          lock => { setWardrobe(lock as ContinuityWardrobe); setWardrobeForm(formFromLock(WARDROBE_FIELDS, lock)); })}
        scopeHint={scopeHintFor(wardrobe, false)}
      />
      <LockCard
        title="Local"
        subtitle="Location Lock — showroom, estúdio, rua, cidade, luz base"
        icon={<MapPin size={16} />}
        fields={LOCATION_FIELDS}
        lock={location}
        loading={loading}
        form={locationForm}
        onForm={setFormValue(setLocationForm)}
        saving={saving === 'location'}
        message={messages.location ?? null}
        onSave={() => save('location',
          () => lockContinuityLocation({
            persona_id: personaId.trim(),
            campaign_id: campaignId.trim() || 'default',
            episode: scopedEpisode(),
            ...locationForm,
          }),
          lock => { setLocation(lock as ContinuityLocation); setLocationForm(formFromLock(LOCATION_FIELDS, lock)); })}
        scopeHint={scopeHintFor(location, false)}
      />
      <LockCard
        title="Veículo"
        subtitle="Vehicle Lock — modelo, cor, placa, rodas, acabamento"
        icon={<Car size={16} />}
        fields={VEHICLE_FIELDS}
        lock={vehicle}
        loading={loading}
        form={vehicleForm}
        onForm={setFormValue(setVehicleForm)}
        saving={saving === 'vehicle'}
        message={messages.vehicle ?? null}
        onSave={() => save('vehicle',
          () => lockContinuityVehicle({
            persona_id: personaId.trim(),
            campaign_id: campaignId.trim() || 'default',
            episode: scopedEpisode(),
            ...vehicleForm,
          }),
          lock => { setVehicle(lock as ContinuityVehicle); setVehicleForm(formFromLock(VEHICLE_FIELDS, lock)); })}
        scopeHint={scopeHintFor(vehicle, false)}
      />
      <LockCard
        title="Voz"
        subtitle="Voice Lock — perfil, emoção, velocidade, intensidade"
        icon={<Mic size={16} />}
        fields={VOICE_FIELDS}
        lock={voice}
        loading={loading}
        form={voiceForm}
        onForm={setFormValue(setVoiceForm)}
        saving={saving === 'voice'}
        message={messages.voice ?? null}
        onSave={() => save('voice',
          () => lockContinuityVoice({ persona_id: personaId.trim(), ...voiceForm }),
          lock => { setVoice(lock as ContinuityVoice); setVoiceForm(formFromLock(VOICE_FIELDS, lock)); })}
        scopeHint={scopeHintFor(null, true)}
      />
    </section>

    <section className="continuity-context" aria-label="Contexto resolvido">
      <header>
        <h2><CheckCircle2 size={15} /> Contexto do episódio</h2>
        {context && (
          context.consistent
            ? <span className="continuity-consistent">consistente</span>
            : <span className="continuity-inconsistent">incompleto</span>
        )}
      </header>
      {contextError && <p className="continuity-form-error">{contextError}</p>}
      {!context && !contextError && <p className="continuity-muted">Resolva o contexto para ver frases, fingerprints e faltas.</p>}
      {context && (
        <div className="continuity-context-body">
          <ul className="continuity-phrases">
            {context.phrases.map(phrase => <li key={phrase}>{phrase}</li>)}
            {context.phrases.length === 0 && <li className="continuity-muted">Nenhuma frase — nada travado.</li>}
          </ul>
          <div className="continuity-signals">
            <p><strong>Fingerprints:</strong> {Object.entries(context.fingerprints).map(([kind, fp]) => `${kind} ${fp}`).join(' · ') || '—'}</p>
            <p><strong>Faltando:</strong> {context.missing.length ? context.missing.join(', ') : 'nada'}</p>
            <p><strong>Drift:</strong> {context.drift.length ? context.drift.join(', ') : 'nenhum'}</p>
          </div>
        </div>
      )}
    </section>

    <section className="continuity-episodes" aria-label="Histórico de episódios">
      <header>
        <h2><ListVideo size={15} /> Histórico de episódios</h2>
      </header>
      {episodesError && <p className="continuity-form-error">{episodesError}</p>}
      <div className="continuity-episode-new">
        <input value={episodeTitle} onChange={event => setEpisodeTitle(event.target.value)} placeholder="Título do novo episódio (opcional)" aria-label="Título do novo episódio" />
        <input value={episodeNotes} onChange={event => setEpisodeNotes(event.target.value)} placeholder="Notas (opcional)" aria-label="Notas do novo episódio" />
        <button type="button" className="primary-button" onClick={createEpisode} disabled={creating}>
          <Plus size={15} /> {creating ? 'Criando…' : 'Criar novo episódio'}
        </button>
      </div>
      {episodeMessage && (
        <p className={episodeMessage.kind === 'ok' ? 'continuity-ok' : 'continuity-form-error'}>{episodeMessage.text}</p>
      )}
      {episodes.length === 0 ? (
        <p className="continuity-muted">Nenhum episódio congelado nesta campanha.</p>
      ) : (
        <ol className="continuity-episode-list">
          {episodes.map(item => {
            const snapshot = item.snapshot as { fingerprints?: Record<string, string>; consistent?: boolean; phrases?: string[] };
            return (
              <li key={item.id}>
                <span className="continuity-episode-number">EP {item.episode}</span>
                <div>
                  <strong>{item.title || `Episódio ${item.episode}`}</strong>
                  {item.notes && <span className="continuity-episode-notes">{item.notes}</span>}
                  <span className="continuity-episode-meta">
                    {Object.entries(snapshot.fingerprints ?? {}).map(([kind, fp]) => `${kind} ${fp}`).join(' · ') || 'sem locks'}
                    {' · '}{snapshot.consistent ? 'consistente' : 'parcial'}
                    {' · '}{item.created_at ? new Date(item.created_at).toLocaleString() : ''}
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  </main>;
}
