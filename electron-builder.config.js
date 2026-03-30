/** @type {import('electron-builder').Configuration} */
module.exports = {
  appId: 'io.caibinet.app',
  productName: 'Caibinet',
  copyright: 'Copyright © 2025 Caibinet',

  directories: {
    buildResources: 'build',
    output: 'release'
  },

  files: [
    'dist/**/*',
    'dist-electron/**/*'
  ],

  extraResources: [
    {
      from: 'dist-core/',
      to: 'core',
      filter: ['**/*']
    }
  ],

  // ─── Linux ───────────────────────────────────────────────────────────────
  linux: {
    target: [
      { target: 'AppImage', arch: ['x64'] },
      { target: 'snap', arch: ['x64'] }
    ],
    category: 'Utility',
    icon: 'build/icons'
  },

  snap: {
    summary: 'Local AI File Organizer powered by Ollama',
    grade: 'stable',
    confinement: 'strict',
    plugs: ['home', 'removable-media', 'network', 'network-bind']
  },

  // ─── Windows ─────────────────────────────────────────────────────────────
  win: {
    target: [
      { target: 'nsis', arch: ['x64'] },
      { target: 'appx', arch: ['x64'] }
    ],
    icon: 'build/icon.ico',
    // Set via WIN_CSC_LINK / WIN_CSC_KEY_PASSWORD env vars in CI
    certificateSubjectName: process.env.WIN_CERT_SUBJECT_NAME
  },

  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true
  },

  appx: {
    // Obtain these values from Microsoft Partner Center after registering the app
    applicationId: 'Caibinet',
    identityName: process.env.APPX_IDENTITY_NAME || 'io.caibinet.app',
    publisher: process.env.APPX_PUBLISHER || 'CN=YourPublisherIdentity',
    publisherDisplayName: 'Caibinet',
    backgroundColor: '#1e293b'
  },

  // ─── macOS ───────────────────────────────────────────────────────────────
  mac: {
    target: [
      { target: 'mas', arch: ['x64', 'arm64'] }
    ],
    category: 'public.app-category.utilities',
    icon: 'build/icon.icns',
    entitlements: 'build/entitlements.mac.plist',
    entitlementsInherit: 'build/entitlements.mac.inherit.plist',
    hardenedRuntime: true,
    gatekeeperAssess: false,
    // Set via CSC_LINK / CSC_KEY_PASSWORD env vars in CI
  },

  mas: {
    entitlements: 'build/entitlements.mas.plist',
    entitlementsInherit: 'build/entitlements.mas.inherit.plist',
    provisioningProfile: 'build/embedded.provisionprofile'
  }
}
