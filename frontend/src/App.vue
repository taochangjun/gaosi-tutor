<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">🧮 小思陪练</div>
      <nav>
        <router-link to="/">孩子模式</router-link>
        <router-link to="/parent">家长模式</router-link>
      </nav>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: var(--card);
  border-bottom: 2px solid var(--border);
}

.brand {
  font-size: 20px;
  font-weight: 800;
  color: var(--primary);
}

nav {
  display: flex;
  gap: 16px;
}

nav a {
  color: var(--muted);
  text-decoration: none;
  font-weight: 600;
}

nav a.router-link-active {
  color: var(--primary);
}
</style>
