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

  linux: {
    target: [{ target: 'AppImage', arch: ['x64'] }],
    category: 'Utility'
  },

  win: {
    target: [{ target: 'nsis', arch: ['x64'] }],
    icon: 'build/icon.ico'
  },

  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true
  }
}
