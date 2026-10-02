"use client";

import { createContext, useContext } from "react";

const SignedInContext = createContext(false);

/** Hands the server's reading of the session cookie to the top bar, so it is right on the first paint. */
export function SignedInProvider({ signedIn, children }: { signedIn: boolean; children: React.ReactNode }) {
  return <SignedInContext.Provider value={signedIn}>{children}</SignedInContext.Provider>;
}

export function useSignedIn(): boolean {
  return useContext(SignedInContext);
}
