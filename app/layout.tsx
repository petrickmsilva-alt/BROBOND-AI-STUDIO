import type { Metadata } from 'next';
import './globals.css';
// V3.2.1 ETAPA 5: the shell always carries one honest status — the
// StatusCenter probes through the retrying network layer.
import StatusCenter from './components/StatusCenter';

export const metadata: Metadata = {
  title: 'BROBOND AI STUDIO',
  description: 'Generative visual workspace for images, video and digital personas.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}<StatusCenter /></body></html>;
}
