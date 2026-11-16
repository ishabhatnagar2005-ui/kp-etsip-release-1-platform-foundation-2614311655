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

export interface PortfolioInput {
  name: string;
  owner: string;
  description: string;
  productArea: string;
  status: 'Active' | 'Archived';
}
export interface Portfolio extends PortfolioInput {
  id: string;
  applicationCount: number;
  qualityScore: number | null;
  createdAt: string;
  updatedAt: string;
}
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export interface ApplicationSummary { id: string; name: string }
