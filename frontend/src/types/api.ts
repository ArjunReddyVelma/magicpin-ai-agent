export interface HealthzResponse {
  status: 'ok';
}

export interface ReadyzResponse {
  status: 'ready';
  checks: Record<string, string>;
}

export interface User {
  id: string;
  full_name: string;
  email: string;
  created_at: string;
}

export interface MerchantProfile {
  id: string;
  business_name: string;
  category: string | null;
  location: string | null;
  description: string | null;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Array<Record<string, unknown>>;
  };
}
