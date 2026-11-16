export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  portfolioAccess: string[];
  defaultLandingPage: 'dashboard' | 'applications' | null;
  mustChangePassword: boolean;
  effectivePermissions?: string[];
}

export interface AdminUser {
  id: string; name: string; email: string; role: string; portfolioAccess: string[];
  status: 'Active' | 'Inactive'; managerName: string | null; vendorIndicator: boolean;
  defaultLandingPage: 'dashboard' | 'applications' | null; authSource: string;
  lastLogin: string | null; createdAt: string; updatedAt: string; mustChangePassword: boolean;
}
export interface AdminRole { id: string; name: string; description: string; permissions: string[]; createdAt: string; updatedAt: string }
export interface AuditEvent { id: string; timestamp: string; userId: string | null; userName: string; action: string; entityType: string; entityId: string | null; details: string }

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

export interface ApplicationInput {
  name: string;
  description: string;
  portfolioId: string;
  productArea: string;
  businessOwner: string;
  technologyOwner: string;
  etsOwner: string;
  criticality: 'Low' | 'Medium' | 'High' | 'Critical';
  tier: number;
  lifecycleStatus: 'Active' | 'Deprecated' | 'Retired';
  technologyStack: string;
  repositoryLink: string | null;
  pipelineLink: string | null;
  applicationHealthScore: number;
  qualityScore: number;
  automationCoverage: number;
  unitTestCoverage: number;
  openDefects: number;
  openCriticalDefects: number;
  riskLevel: 'Low' | 'Medium' | 'High';
}
export interface Application extends ApplicationInput {
  id: string;
  createdAt: string;
  updatedAt: string;
}

export interface DashboardPortfolio {
  id: string;
  name: string;
  applicationCount: number;
  qualityScore: number | null;
  applicationsAtRisk: number;
}

export interface DashboardMetrics {
  enterpriseQualityScore: number | null;
  applicationHealthScore: number | null;
  automationMaturityScore: number | null;
  openCriticalDefects: number;
  applicationsAtRisk: number;
  totalApplications: number;
  totalPortfolios: number;
  portfolios: DashboardPortfolio[];
}
