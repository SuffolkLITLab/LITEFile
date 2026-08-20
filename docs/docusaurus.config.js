// @ts-check
// Note: type annotations allow type checking and IDEs autocompletion

import { themes as prismThemes } from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'LITEFile',
  tagline: 'Streamlined, plain-language electronic court filing and platform',
  favicon: 'img/favicon.ico',

  // Set the production url of your site here
  url: 'https://litefile-docs.suffolklitlab.org',
  // Set the /<baseUrl>/ pathname under which your site is served
  baseUrl: '/',

  // GitHub pages deployment config.
  organizationName: 'SuffolkLITLab',
  projectName: 'LITEFile',

  onBrokenLinks: 'throw',
  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },
  themes: ['@docusaurus/theme-mermaid'],

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: './sidebars.js',
          routeBasePath: 'docs',
          editUrl: 'https://github.com/SuffolkLITLab/LITEFile/tree/main/docs/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      navbar: {
        title: 'LITEFile',
        logo: {
          alt: 'Suffolk LIT Lab Logo',
          src: 'img/lit-lab-logo-small-inverted.svg',
          srcDark: 'img/lit-lab-logo-small-inverted.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'userGuide',
            position: 'left',
            label: 'User guide',
          },
          {
            type: 'docSidebar',
            sidebarId: 'partnersCourts',
            position: 'left',
            label: 'Partner & court guide',
          },
          {
            type: 'docSidebar',
            sidebarId: 'adminGuide',
            position: 'left',
            label: 'Admin & deployment',
          },
          {
            href: 'https://assemblyline.suffolklitlab.org',
            label: 'AssemblyLine',
            position: 'right',
          },
          {
            href: 'https://suffolklitlab.org',
            label: 'Suffolk LIT Lab',
            position: 'right',
          },
          {
            href: 'https://www.givecampus.com/campaigns/70271/donations/new',
            label: 'Donate',
            position: 'right',
            className: 'navbar-donate-button',
          },
          {
            href: 'https://github.com/SuffolkLITLab/LITEFile',
            className: 'header-github-link',
            'aria-label': 'GitHub repository',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'light',
        links: [
          {
            title: 'Documentation',
            items: [
              {
                label: 'End-user guide',
                to: '/docs/user-guide/overview',
              },
              {
                label: 'Partner & court guide (WIP)',
                to: '/docs/partners-courts',
              },
              {
                label: 'Admin & deployment (WIP)',
                to: '/docs/admin',
              },
            ],
          },
          {
            title: 'Suffolk LIT Lab',
            items: [
              {
                label: 'Suffolk LIT Lab home',
                href: 'https://suffolklitlab.org',
              },
              {
                label: 'Document Assembly Line',
                href: 'https://assemblyline.suffolklitlab.org',
              },
              {
                label: 'Legal tech course',
                href: 'https://suffolklitlab.org/legal-tech-class/',
              },
              {
                label: 'Docassemble documentation',
                href: 'https://docassemble.org/docs.html',
              },
            ],
          },
          {
            title: 'Community & code',
            items: [
              {
                label: 'GitHub repository',
                href: 'https://github.com/SuffolkLITLab/LITEFile',
              },
              {
                label: 'Report an issue',
                href: 'https://github.com/SuffolkLITLab/LITEFile/issues',
              },
              {
                label: 'Donate to LIT Lab',
                href: 'https://www.givecampus.com/campaigns/70271/donations/new',
              },
            ],
          },
        ],
        copyright: `<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-NC-SA 4.0</a> | Developed by the <a href="https://suffolklitlab.org/" target="_blank" rel="noopener noreferrer">Suffolk University Law School Legal Innovation & Technology Lab</a>. Built with <a href="https://docusaurus.io/" target="_blank" rel="noopener noreferrer">Docusaurus</a>.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
        additionalLanguages: ['python', 'bash', 'json', 'yaml', 'toml', 'docker'],
      },
    }),
};

export default config;
