export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  portfolioAccess: string[];
  defaultLandingPage: 'dashboard' | 'applications' | null;
  mustChangePassword: boolean;
}

export interface LoginResponse { token: string; user: User }
