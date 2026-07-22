import { defineConfig } from 'vitepress'
import deviceSidebar from './device-sidebar.json'

// Structure and layout closely follow upstream EspControl's docs
// (github.com/jtenniswood/espcontrol) so users move between the two sites
// without relearning navigation.
const hostname = 'https://lamiskin.github.io/espcontrol-community-devices/'

export default defineConfig({
  title: 'EspControl Community Devices',
  description:
    'Unofficial community-maintained EspControl firmware for ESP32 touchscreen panels not officially supported upstream.',
  base: '/espcontrol-community-devices/',
  outDir: '../community-pages',
  srcExclude: ['parts/**'],
  cleanUrls: true,
  lastUpdated: false,

  head: [
    ['meta', { property: 'og:site_name', content: 'EspControl Community Devices' }],
    ['meta', { property: 'og:url', content: hostname }],
  ],

  themeConfig: {
    nav: [
      { text: 'Install', link: '/getting-started/install' },
      {
        text: 'Issues',
        link: 'https://github.com/lamiskin/espcontrol-community-devices/issues',
      },
      {
        text: 'GitHub',
        link: 'https://github.com/lamiskin/espcontrol-community-devices',
      },
      {
        text: 'Upstream Docs',
        link: 'https://jtenniswood.github.io/espcontrol/',
      },
    ],

    sidebar: [
      {
        text: 'Getting Started',
        items: [
          { text: 'Overview', link: '/' },
          { text: 'Install', link: '/getting-started/install' },
          { text: 'Updates', link: '/getting-started/updates' },
        ],
      },
      {
        text: 'Community Devices',
        items: deviceSidebar,
      },
      {
        text: 'Reference',
        items: [
          { text: 'Support Policy', link: '/reference/support-policy' },
          { text: 'Device Graduation', link: '/reference/graduation' },
          { text: 'Download Stats', link: '/reference/download-stats' },
          {
            text: 'Device Status Table',
            link: 'https://github.com/lamiskin/espcontrol-community-devices/blob/main/community/STATUS.md',
          },
          {
            text: 'Adding a Device',
            link: 'https://github.com/lamiskin/espcontrol-community-devices/blob/main/community/docs/adding-a-device.md',
          },
        ],
      },
    ],

    outline: { level: [2, 3] },
    socialLinks: [
      {
        icon: 'github',
        link: 'https://github.com/lamiskin/espcontrol-community-devices',
      },
    ],
    footer: {
      message:
        'Unofficial community project. Not affiliated with or supported by the upstream EspControl project.',
    },
  },
})
