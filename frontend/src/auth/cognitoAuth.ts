import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession,
} from "amazon-cognito-identity-js";

const memoryStore: Record<string, string> = {};

const inMemoryStorage = {
  setItem(key: string, value: string) {
    memoryStore[key] = value;
  },
  getItem(key: string) {
    return memoryStore[key] ?? null;
  },
  removeItem(key: string) {
    delete memoryStore[key];
  },
  clear() {
    for (const key of Object.keys(memoryStore)) {
      delete memoryStore[key];
    }
  },
};

const userPool = new CognitoUserPool({
  UserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
  ClientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
  Storage: inMemoryStorage,
});

let currentUser: CognitoUser | null = null;
let pendingChallengeUser: CognitoUser | null = null;
let pendingLoginEmail: string | null = null;
let cachedSession: CognitoUserSession | null = null;

function createCognitoUser(email: string): CognitoUser {
  return new CognitoUser({
    Username: email.trim().toLowerCase(),
    Pool: userPool,
    Storage: inMemoryStorage,
  });
}

function sessionFromUser(user: CognitoUser): Promise<CognitoUserSession> {
  return new Promise((resolve, reject) => {
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session) {
        reject(err ?? new Error("No active session"));
        return;
      }
      resolve(session);
    });
  });
}

function refreshSession(user: CognitoUser, session: CognitoUserSession): Promise<CognitoUserSession> {
  return new Promise((resolve, reject) => {
    user.refreshSession(session.getRefreshToken(), (err, refreshed) => {
      if (err || !refreshed) {
        reject(err ?? new Error("Failed to refresh session"));
        return;
      }
      cachedSession = refreshed;
      resolve(refreshed);
    });
  });
}

function emailFromSession(session: CognitoUserSession): string | null {
  const payload = session.getIdToken().decodePayload();
  if (typeof payload.email === "string" && payload.email.includes("@")) {
    return payload.email;
  }
  const preferred = payload.preferred_username;
  if (typeof preferred === "string" && preferred.includes("@")) {
    return preferred;
  }
  const username = payload["cognito:username"];
  if (typeof username === "string" && username.includes("@")) {
    return username;
  }
  return null;
}

function resolveEmail(session: CognitoUserSession, user: CognitoUser): string {
  return emailFromSession(session) ?? pendingLoginEmail ?? user.getUsername();
}

export async function getIdToken(): Promise<string | null> {
  const user = currentUser ?? userPool.getCurrentUser();
  if (!user) return null;

  currentUser = user;

  try {
    if (cachedSession?.isValid()) {
      return cachedSession.getIdToken().getJwtToken();
    }

    let session = await sessionFromUser(user);
    if (!session.isValid()) {
      session = await refreshSession(user, session);
    } else {
      cachedSession = session;
    }
    return session.getIdToken().getJwtToken();
  } catch {
    if (cachedSession?.getIdToken()) {
      return cachedSession.getIdToken().getJwtToken();
    }
    return null;
  }
}

export function getPendingChallengeUser(): CognitoUser | null {
  return pendingChallengeUser;
}

export function signIn(
  email: string,
  password: string,
): Promise<{ challenge: "FORCE_CHANGE_PASSWORD" | null; email: string }> {
  const normalizedEmail = email.trim().toLowerCase();

  return new Promise((resolve, reject) => {
    const cognitoUser = createCognitoUser(normalizedEmail);
    const authDetails = new AuthenticationDetails({
      Username: normalizedEmail,
      Password: password,
    });

    cognitoUser.authenticateUser(authDetails, {
      onSuccess: (session) => {
        currentUser = cognitoUser;
        pendingChallengeUser = null;
        pendingLoginEmail = normalizedEmail;
        cachedSession = session;
        resolve({ challenge: null, email: resolveEmail(session, cognitoUser) });
      },
      onFailure: (err) => {
        reject(err);
      },
      newPasswordRequired: () => {
        pendingChallengeUser = cognitoUser;
        pendingLoginEmail = normalizedEmail;
        cachedSession = null;
        resolve({ challenge: "FORCE_CHANGE_PASSWORD", email: normalizedEmail });
      },
    });
  });
}

export function completeNewPassword(newPassword: string): Promise<{ email: string }> {
  const user = pendingChallengeUser;
  if (!user) {
    return Promise.reject(new Error("No pending password challenge"));
  }

  return new Promise((resolve, reject) => {
    user.completeNewPasswordChallenge(
      newPassword,
      {},
      {
        onSuccess: (session) => {
          currentUser = user;
          pendingChallengeUser = null;
          cachedSession = session;
          const email = resolveEmail(session, user);
          resolve({ email });
        },
        onFailure: (err) => {
          reject(err);
        },
      },
    );
  });
}

export async function signOut(): Promise<void> {
  const user = currentUser ?? userPool.getCurrentUser();
  if (user) {
    user.signOut();
  }
  currentUser = null;
  pendingChallengeUser = null;
  pendingLoginEmail = null;
  cachedSession = null;
  inMemoryStorage.clear();
}

export async function restoreSession(): Promise<string | null> {
  const user = userPool.getCurrentUser();
  if (!user) return null;

  currentUser = user;
  const token = await getIdToken();
  if (!token) {
    currentUser = null;
    cachedSession = null;
    return null;
  }

  if (cachedSession) {
    return resolveEmail(cachedSession, user);
  }

  try {
    const session = await sessionFromUser(user);
    cachedSession = session;
    return resolveEmail(session, user);
  } catch {
    return pendingLoginEmail ?? user.getUsername();
  }
}

export async function getCurrentUserEmail(): Promise<string | null> {
  const user = currentUser ?? userPool.getCurrentUser();
  if (!user) return null;

  if (cachedSession) {
    return resolveEmail(cachedSession, user);
  }

  try {
    const session = await sessionFromUser(user);
    cachedSession = session;
    return resolveEmail(session, user);
  } catch {
    return pendingLoginEmail ?? user.getUsername();
  }
}
