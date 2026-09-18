/**
 * PR009.6 — Premium Login Experience: the login screen's bilingual copy.
 *
 * The studio shell speaks English, but the login experience is the brand's
 * front door and ships in Portuguese by default, with a discrete PT/EN
 * switch in the top-right corner. This module is pure data: one key per
 * screen string, PT and EN in lockstep — the companion contract test
 * asserts the two dictionaries never drift and that the exact brand
 * strings (título, subtítulo, botões, rodapé) stay verbatim.
 */

export type LoginLanguage = 'pt' | 'en';

export type LoginCopy = {
  /** Discreet top bar over the hero: "IA • CINEMA • MARCA • IMPACTO". */
  topBar: string;
  /** Brand line under the logo. */
  eyebrow: string;
  title: string;
  subtitle: string;
  cardTitle: string;
  cardSubtitle: string;
  email: string;
  emailPlaceholder: string;
  password: string;
  passwordPlaceholder: string;
  showPassword: string;
  hidePassword: string;
  remember: string;
  rememberHint: string;
  forgot: string;
  forgotNotice: string;
  signIn: string;
  orDivider: string;
  google: string;
  googleNotice: string;
  noAccount: string;
  createAccount: string;
  hasAccount: string;
  backToLogin: string;
  registerTitle: string;
  registerSubtitle: string;
  registerButton: string;
  fullName: string;
  fullNamePlaceholder: string;
  connecting: string;
  continueAs: string;
  signedInSubtitle: string;
  signOut: string;
  backToStudio: string;
  version: string;
  online: string;
  offline: string;
  closeLabel: string;
  heroAlt: string;
  /** The five studio pillars shown on the hero (grid / carousel). */
  features: Array<{ title: string; subtitle: string }>;
};

export const LOGIN_COPY: Record<LoginLanguage, LoginCopy> = {
  pt: {
    topBar: 'IA • CINEMA • MARCA • IMPACTO',
    eyebrow: 'BROBOND WEAR',
    title: 'Transforme ideias em grandes campanhas.',
    subtitle: 'O estúdio de IA da Brobond para criação, produção e gestão de conteúdo visual e audiovisual de alto impacto.',
    cardTitle: 'Bem-vindo de volta',
    cardSubtitle: 'Entre no seu estúdio e continue criando o extraordinário.',
    email: 'Email',
    emailPlaceholder: 'seu@email.com',
    password: 'Senha',
    passwordPlaceholder: 'Sua senha',
    showPassword: 'Mostrar senha',
    hidePassword: 'Esconder senha',
    remember: 'Lembrar de mim',
    rememberHint: 'Sua sessão fica salva por 30 dias neste dispositivo.',
    forgot: 'Esqueceu sua senha?',
    forgotNotice: 'A recuperação de senha chega em breve. Por enquanto, entre com seu email e senha.',
    signIn: 'Entrar no Brobond Studio',
    orDivider: 'ou',
    google: 'Entrar com Google',
    googleNotice: 'Login com Google ainda não está configurado neste ambiente.',
    noAccount: 'Ainda não tem uma conta?',
    createAccount: 'Criar conta',
    hasAccount: 'Já tem uma conta?',
    backToLogin: 'Voltar ao login',
    registerTitle: 'Crie seu estúdio',
    registerSubtitle: 'Comece a construir seu estúdio visual privado.',
    registerButton: 'Criar minha conta',
    fullName: 'Nome completo',
    fullNamePlaceholder: 'Como devemos te chamar?',
    connecting: 'Conectando ao workspace…',
    continueAs: 'Continuar como',
    signedInSubtitle: 'Sessão ativa no Brobond Studio.',
    signOut: 'Sair',
    backToStudio: 'Voltar ao studio',
    version: 'Brobond Studio v4.0.1',
    online: 'Sistema Online',
    offline: 'Sistema Offline',
    closeLabel: 'Fechar',
    heroAlt: 'Fundador da Brobond ao lado da RAM 2026',
    features: [
      { title: 'Diretor IA', subtitle: 'Direção completa a partir de um briefing.' },
      { title: 'Storyboard', subtitle: 'Cenas numeradas prontas para produção.' },
      { title: 'Imagem & Vídeo', subtitle: 'Geração cinematográfica de alta qualidade.' },
      { title: 'Assets', subtitle: 'Biblioteca centralizada do projeto.' },
      { title: 'Quality', subtitle: 'Controle de qualidade automatizado.' },
    ],
  },
  en: {
    topBar: 'AI • CINEMA • BRAND • IMPACT',
    eyebrow: 'BROBOND WEAR',
    title: 'Turn ideas into great campaigns.',
    subtitle: "Brobond's AI studio for creating, producing and managing high-impact visual and audiovisual content.",
    cardTitle: 'Welcome back',
    cardSubtitle: 'Enter your studio and keep creating the extraordinary.',
    email: 'Email',
    emailPlaceholder: 'you@email.com',
    password: 'Password',
    passwordPlaceholder: 'Your password',
    showPassword: 'Show password',
    hidePassword: 'Hide password',
    remember: 'Remember me',
    rememberHint: 'Your session stays saved for 30 days on this device.',
    forgot: 'Forgot your password?',
    forgotNotice: 'Password recovery is coming soon. For now, sign in with your email and password.',
    signIn: 'Sign in to Brobond Studio',
    orDivider: 'or',
    google: 'Sign in with Google',
    googleNotice: 'Google sign-in is not configured in this environment yet.',
    noAccount: 'No account yet?',
    createAccount: 'Create account',
    hasAccount: 'Already have an account?',
    backToLogin: 'Back to sign in',
    registerTitle: 'Create your studio',
    registerSubtitle: 'Start building your private visual studio.',
    registerButton: 'Create my account',
    fullName: 'Full name',
    fullNamePlaceholder: 'What should we call you?',
    connecting: 'Connecting to workspace…',
    continueAs: 'Continue as',
    signedInSubtitle: 'Active session in Brobond Studio.',
    signOut: 'Sign out',
    backToStudio: 'Back to studio',
    version: 'Brobond Studio v4.0.1',
    online: 'System Online',
    offline: 'System Offline',
    closeLabel: 'Close',
    heroAlt: 'Brobond founder beside the RAM 2026',
    features: [
      { title: 'AI Director', subtitle: 'Full direction from a single brief.' },
      { title: 'Storyboard', subtitle: 'Numbered scenes ready for production.' },
      { title: 'Image & Video', subtitle: 'Cinematic generation in high quality.' },
      { title: 'Assets', subtitle: 'Centralized project library.' },
      { title: 'Quality', subtitle: 'Automated quality control.' },
    ],
  },
};
