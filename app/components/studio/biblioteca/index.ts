/**
 * PR009.7 — Biblioteca Criativa. O orquestrador é `Biblioteca`; o resto são
 * suas peças públicas (testadas isoladamente para continuarem honestas).
 *
 * Interface apenas: nenhuma rota, endpoint, JWT, upload ou tabela muda —
 * as APIs continuam em `/api/v1/assets`.
 */
export { Biblioteca } from './biblioteca';
export { BibliotecaHeader } from './biblioteca-header';
export { BibliotecaSidebar } from './biblioteca-sidebar';
export { BibliotecaCard, BibliotecaGrid, cardThumbnail } from './biblioteca-card';
export { BibliotecaDropZone, BibliotecaDropHint, BibliotecaUploadQueue } from './biblioteca-dropzone';
export { BibliotecaPreview } from './biblioteca-preview';
export { BibliotecaState, STATE_COPY } from './biblioteca-states';
export type { BibliotecaStateId } from './biblioteca-states';
