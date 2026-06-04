// Auth API client — communicates with Flask /api/auth/* endpoints
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export interface AuthUser {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
  avatar_url: string | null;
  group_id: string | null;
  email_verified: boolean;
  settings: {
    language: string;
    theme: string;
    notification_enabled: boolean;
  };
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface AuthResponse {
  status: "success" | "error";
  message: string;
  token?: string;
  user?: AuthUser;
}

/**
 * Register a new account.
 */
export async function registerUser(data: {
  email: string;
  username: string;
  password: string;
  full_name?: string;
}): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const json: AuthResponse = await res.json();
  if (!res.ok) throw new Error(json.message || "Đăng ký thất bại");
  return json;
}

/**
 * Login with email/username + password.
 */
export async function loginUser(
  identifier: string,
  password: string
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifier, password }),
  });
  const json: AuthResponse = await res.json();
  if (!res.ok) throw new Error(json.message || "Đăng nhập thất bại");
  return json;
}

/**
 * Fetch the current authenticated user.
 */
export async function fetchCurrentUser(
  token: string
): Promise<AuthUser | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
    if (!res.ok) return null;
    const json = await res.json();
    return json.user ?? null;
  } catch {
    return null;
  }
}

/**
 * Update current user profile (group_id, settings, etc.).
 */
export async function updateProfile(
  token: string,
  data: { group_id?: string | null; full_name?: string; settings?: object }
): Promise<AuthUser> {
  const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.message || "Cập nhật thất bại");
  return json.user;
}

/**
 * Request sending a verification OTP code to current user's email.
 */
export async function sendVerificationCode(token: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/send-verification`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });
  const json: AuthResponse = await res.json();
  if (!res.ok) throw new Error(json.message || "Gửi mã xác thực thất bại");
  return json;
}

/**
 * Verify the user's email using the OTP code.
 */
export async function verifyEmail(token: string, code: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/verify-email`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ code }),
  });
  const json: AuthResponse = await res.json();
  if (!res.ok) throw new Error(json.message || "Xác thực email thất bại");
  return json;
}

/**
 * Request a password reset OTP code.
 */
export async function forgotPassword(email: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  const json: AuthResponse = await res.json();
  if (!res.ok) throw new Error(json.message || "Gửi mã khôi phục thất bại");
  return json;
}

/**
 * Reset password using the reset OTP code.
 */
export async function resetPassword(data: {
  email: string;
  code: string;
  new_password: string;
}): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const json: AuthResponse = await res.json();
  if (!res.ok) throw new Error(json.message || "Đặt lại mật khẩu thất bại");
  return json;
}
