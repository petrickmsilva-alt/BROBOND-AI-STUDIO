// @vitest-environment jsdom
/**
 * PR013 — V4.0.1 · ETAPA 1 — the drop surface and the queue list.
 *
 * The overlay must appear on a real dragenter, survive child boundaries
 * (the depth counter), and disappear on drop; the queue must print percent,
 * speed, size and the four statuses exactly — never a simulated value.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { UploadItem } from '../../../../lib/assets/library';
import {
  createUploadItem,
  markUploading,
  progressUpload,
  completeUpload,
  failUpload,
} from '../../../../lib/assets/library';
import { AssetBrowseButton, AssetDropZone, UploadQueueList } from './upload-zone';

function dragData(files: File[] = []) {
  return {
    dataTransfer: {
      files,
      types: ['Files'],
      dropEffect: '',
    },
  };
}

const png = () => new File(['x'.repeat(10)], 'frame.png', { type: 'image/png' });

describe('AssetDropZone', () => {
  it('shows the overlay while files hover over the area', () => {
    render(<AssetDropZone onFiles={() => undefined}><div>body</div></AssetDropZone>);
    expect(screen.queryByTestId('al-drop-overlay')).toBeNull();
    fireEvent.dragEnter(screen.getByTestId('al-dropzone'), dragData());
    expect(screen.getByTestId('al-drop-overlay')).toBeInTheDocument();
    expect(screen.getByText('Drop to add to the library')).toBeInTheDocument();
    fireEvent.dragLeave(screen.getByTestId('al-dropzone'), dragData());
    expect(screen.queryByTestId('al-drop-overlay')).toBeNull();
  });

  it('keeps the overlay across nested boundaries (depth counter) and hides at depth zero', () => {
    render(<AssetDropZone onFiles={() => undefined}><div>body</div></AssetDropZone>);
    const zone = screen.getByTestId('al-dropzone');
    fireEvent.dragEnter(zone, dragData());
    fireEvent.dragEnter(zone, dragData());
    fireEvent.dragLeave(zone, dragData());
    expect(screen.getByTestId('al-drop-overlay')).toBeInTheDocument();
    fireEvent.dragLeave(zone, dragData());
    expect(screen.queryByTestId('al-drop-overlay')).toBeNull();
    // The counter never goes negative: an extra dragleave is a no-op.
    fireEvent.dragLeave(zone, dragData());
    fireEvent.dragEnter(zone, dragData());
    expect(screen.getByTestId('al-drop-overlay')).toBeInTheDocument();
  });

  it('ignores drags that do not carry files', () => {
    render(<AssetDropZone onFiles={() => undefined}><div>body</div></AssetDropZone>);
    fireEvent.dragEnter(screen.getByTestId('al-dropzone'), { dataTransfer: { files: [], types: ['text/plain'], dropEffect: '' } });
    expect(screen.queryByTestId('al-drop-overlay')).toBeNull();
  });

  it('emits the dropped files and resets the drag state', () => {
    const onFiles = vi.fn();
    render(<AssetDropZone onFiles={onFiles}><div>body</div></AssetDropZone>);
    const zone = screen.getByTestId('al-dropzone');
    fireEvent.dragEnter(zone, dragData());
    fireEvent.drop(zone, dragData([png()]));
    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0].map((file: File) => file.name)).toEqual(['frame.png']);
    expect(screen.queryByTestId('al-drop-overlay')).toBeNull();
  });

  it('does not call onFiles for an empty drop', () => {
    const onFiles = vi.fn();
    render(<AssetDropZone onFiles={onFiles}><div>body</div></AssetDropZone>);
    fireEvent.drop(screen.getByTestId('al-dropzone'), dragData([]));
    expect(onFiles).not.toHaveBeenCalled();
  });

  it('emits picked files through the hidden input and clears its value for re-pick', () => {
    const onFiles = vi.fn();
    render(<AssetDropZone onFiles={onFiles}><div>body</div></AssetDropZone>);
    const input = screen.getByLabelText('Select files to upload') as HTMLInputElement;
    expect(input).toHaveAttribute('accept', '.png,.jpg,.jpeg,.webp,.mp4,.mov');
    fireEvent.change(input, { target: { files: [png()] } });
    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(input.value).toBe('');
  });

  it('blocks everything while disabled', () => {
    const onFiles = vi.fn();
    render(<AssetDropZone onFiles={onFiles} disabled><div>body</div></AssetDropZone>);
    const zone = screen.getByTestId('al-dropzone');
    fireEvent.dragEnter(zone, dragData());
    expect(screen.queryByTestId('al-drop-overlay')).toBeNull();
    fireEvent.drop(zone, dragData([png()]));
    fireEvent.change(screen.getByLabelText('Select files to upload'), { target: { files: [png()] } });
    expect(onFiles).not.toHaveBeenCalled();
  });

  it('marks copy as the drop effect while hovering', () => {
    render(<AssetDropZone onFiles={() => undefined}><div>body</div></AssetDropZone>);
    const zone = screen.getByTestId('al-dropzone');
    const data = dragData();
    fireEvent.dragOver(zone, data);
    expect(data.dataTransfer.dropEffect).toBe('copy');
  });

});

describe('AssetBrowseButton', () => {
  it('opens its own picker and forwards the selection', () => {
    const onFiles = vi.fn();
    render(<AssetBrowseButton onFiles={onFiles} />);
    expect(screen.getByRole('button', { name: /Upload files/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Select files to upload'), { target: { files: [png()] } });
    expect(onFiles).toHaveBeenCalledTimes(1);
  });

  it('clicks through to the hidden input', () => {
    render(<AssetBrowseButton onFiles={() => undefined} />);
    const input = screen.getByLabelText('Select files to upload') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, 'click');
    fireEvent.click(screen.getByRole('button', { name: /Upload files/ }));
    expect(clickSpy).toHaveBeenCalled();
  });

  it('accepts a custom label and ignores empty selections', () => {
    const onFiles = vi.fn();
    render(<AssetBrowseButton onFiles={onFiles} label="Upload assets" />);
    expect(screen.getByRole('button', { name: /Upload assets/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Select files to upload'), { target: { files: [] } });
    expect(onFiles).not.toHaveBeenCalled();
  });
});

describe('UploadQueueList', () => {
  const file = { name: 'take-01.mp4', type: 'video/mp4', size: 1_572_864 };

  it('renders nothing with an empty queue', () => {
    const { container } = render(<UploadQueueList items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows percent and live speed while uploading', () => {
    let item = createUploadItem('up-1', file, 'video');
    item = markUploading(item);
    item = progressUpload(item, 786_432, 1_572_864, 1_048_576);
    render(<UploadQueueList items={[item]} />);
    expect(screen.getByText('take-01.mp4')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('1.0 MB/s')).toBeInTheDocument();
    expect(screen.getByText('1.5 MB')).toBeInTheDocument();
    expect(screen.getByText('Uploading')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');
  });

  it('prints every status of the machine with its own emblem', () => {
    const items: UploadItem[] = [
      { ...createUploadItem('a', { ...file, name: 'a.png' }, 'image') },
      (() => { const base = createUploadItem('b', { ...file, name: 'b.mov' }, 'video'); return completeUpload(markUploading(base)); })(),
      failUpload(createUploadItem('c', { ...file, name: 'c.png' }, 'image'), 'Server answered 415'),
    ];
    render(<UploadQueueList items={items} />);
    expect(screen.getByText('Queued')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('Server answered 415')).toBeInTheDocument();
    // Outside an in-flight upload the speed field is the honest dash.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});
