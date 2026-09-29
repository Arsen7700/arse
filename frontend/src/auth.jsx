import React, { createContext, useContext } from "react";

export const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

export function roleLabel(role) {
  return ({ admin: "Администратор", lead: "Ведущий", specialist: "Специалист", cashier: "Кассир" })[role] || role;
}
