import NextAuth, { type NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";

/**
 * Google sign-in is the product's auth method. The Credentials "demo" provider
 * exists ONLY for local development (AUTH_DEV_LOGIN=true) so the full signed-in
 * dashboard can be exercised before Google OAuth credentials are configured.
 * It must never be enabled in production.
 */
export const googleConfigured = Boolean(
  process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET,
);

export const devLoginEnabled =
  process.env.AUTH_DEV_LOGIN === "true" &&
  process.env.NODE_ENV !== "production";

const providers: NextAuthConfig["providers"] = [];

if (googleConfigured) {
  providers.push(
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  );
}

if (devLoginEnabled) {
  providers.push(
    Credentials({
      id: "dev-login",
      name: "Demo account",
      credentials: {},
      async authorize() {
        return {
          id: "demo-user",
          name: "Daniel Adewale",
          email: "demo@emploihq.com",
          image: null,
        };
      },
    }),
  );
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  // Vercel / custom-domain: trust the Host header so the session cookie is
  // issued for the URL the browser actually used (app.emploihq.com), not a
  // stale AUTH_URL pointing at a preview deployment.
  trustHost: true,
  session: { strategy: "jwt" },
  pages: { signIn: "/login", signOut: "/signout" },
  callbacks: {
    jwt({ token, user }) {
      if (user?.id) token.sub = user.id;
      if (user?.email) token.email = user.email;
      if (user?.name) token.name = user.name;
      return token;
    },
    session({ session, token }) {
      if (token.sub) session.user.id = token.sub;
      if (token.email && session.user) session.user.email = token.email as string;
      if (token.name && session.user) session.user.name = token.name as string;
      return session;
    },
  },
});
