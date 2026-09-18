/**
 * PR009.6 — Premium Login Experience: the login screen's bilingual copy.
 *
 * PR009.6.1 (Pixel Perfect Login) replaces the previous interpretation with
 * the approved mockup, verbatim: the hero top bar carries the brand line on
 * the left and "CRIATIVIDADE VESTE O FUTURO" on the right, the five studio
 * pillars carry the short uppercase captions of the mockup (CONCEITO,
 * PLANEJAMENTO, GERAÇÃO, BIBLIOTECA, APROVAÇÃO), and the card reads exactly
 * as designed ("E-mail ou usuário", "ou continue com", "Ainda não tem uma
 * conta? Criar conta").
 *
 * The studio shell speaks English, but the login experience is the brand's
 * front door and ships in Portuguese by default, with a discrete PT/EN
 * switch in the card's top-right corner. This module is pure data: one key
 * per screen string, PT and EN in lockstep — the companion contract test
 * asserts the two dictionaries never drift and that the exact brand strings
 * (título, subtítulo, botões, rodapé) stay verbatim.
 */

export type LoginLanguage = 'pt' | 'en';

export type LoginCopy = {
  /** Discreet top bar over the hero, left: "IA • CINEMA • MARCA • IMPACTO". */
  topBar: string;
  /** Same bar, right: "CRIATIVIDADE VESTE O FUTURO". */
  topBarRight: string;
  /** Brand line under the logo (kept for the brand lockup contract). */
  eyebrow: string;
  title: string;
  /** The hero title, split exactly as the mockup sets it: white line… */
  titleLead: string;
  /** …then the gold line. `titleLead + ' ' + titleAccent === title`. */
  titleAccent: string;
  subtitle: string;
  /** Hero footer accent under the five pillars. */
  tagline: string;
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
  languageLabel: string;
  heroAlt: string;
  /** The five studio pillars shown on the hero footer (five equal cards). */
  features: Array<{ title: string; subtitle: string }>;
};

export const LOGIN_COPY: Record<LoginLanguage, LoginCopy> = {
  pt: {
    topBar: 'IA • CINEMA • MARCA • IMPACTO',
    topBarRight: 'CRIATIVIDADE VESTE O FUTURO',
    eyebrow: 'BROBOND WEAR',
    title: 'Transforme ideias em grandes campanhas.',
    titleLead: 'Transforme ideias em',
    titleAccent: 'grandes campanhas.',
    subtitle: 'O estúdio de IA da Brobond para criação, produção e gestão de conteúdo visual e audiovisual de alto impacto.',
    tagline: 'MAIS QUE ESTILO, UMA VISÃO',
    cardTitle: 'Bem-vindo de volta',
    cardSubtitle: 'Entre no seu estúdio e continue criando o extraordinário.',
    email: 'Email',
    emailPlaceholder: 'E-mail ou usuário',
    password: 'Senha',
    passwordPlaceholder: 'Senha',
    showPassword: 'Mostrar senha',
    hidePassword: 'Esconder senha',
    remember: 'Lembrar de mim',
    rememberHint: 'Sua sessão fica salva por 30 dias neste dispositivo.',
    forgot: 'Esqueceu sua senha?',
    forgotNotice: 'A recuperação de senha chega em breve. Por enquanto, entre com seu email e senha.',
    signIn: 'Entrar no Brobond Studio',
    orDivider: 'ou continue com',
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
    languageLabel: 'Idioma',
    heroAlt: 'Fundador da Brobond ao lado da RAM 2026',
    features: [
      { title: 'Diretor IA', subtitle: 'CONCEITO' },
      { title: 'Storyboard', subtitle: 'PLANEJAMENTO' },
      { title: 'Imagem & Vídeo', subtitle: 'GERAÇÃO' },
      { title: 'Assets', subtitle: 'BIBLIOTECA' },
      { title: 'Quality', subtitle: 'APROVAÇÃO' },
    ],
  },
  en: {
    topBar: 'AI • CINEMA • BRAND • IMPACT',
    topBarRight: 'CREATIVITY WEARS THE FUTURE',
    eyebrow: 'BROBOND WEAR',
    title: 'Turn ideas into great campaigns.',
    titleLead: 'Turn ideas into',
    titleAccent: 'great campaigns.',
    subtitle: "Brobond's AI studio for creating, producing and managing high-impact visual and audiovisual content.",
    tagline: 'MORE THAN STYLE, A VISION',
    cardTitle: 'Welcome back',
    cardSubtitle: 'Enter your studio and keep creating the extraordinary.',
    email: 'Email',
    emailPlaceholder: 'E-mail or username',
    password: 'Password',
    passwordPlaceholder: 'Password',
    showPassword: 'Show password',
    hidePassword: 'Hide password',
    remember: 'Remember me',
    rememberHint: 'Your session stays saved for 30 days on this device.',
    forgot: 'Forgot your password?',
    forgotNotice: 'Password recovery is coming soon. For now, sign in with your email and password.',
    signIn: 'Sign in to Brobond Studio',
    orDivider: 'or continue with',
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
    languageLabel: 'Language',
    heroAlt: 'Brobond founder beside the RAM 2026',
    features: [
      { title: 'AI Director', subtitle: 'CONCEPT' },
      { title: 'Storyboard', subtitle: 'PLANNING' },
      { title: 'Image & Video', subtitle: 'GENERATION' },
      { title: 'Assets', subtitle: 'LIBRARY' },
      { title: 'Quality', subtitle: 'APPROVAL' },
    ],
  },
};
