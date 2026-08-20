// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  userGuide: [
    {
      type: 'category',
      label: 'End-user guide',
      collapsed: false,
      items: [
        'user-guide/overview',
        'user-guide/before-you-begin',
        'user-guide/walkthrough',
        'user-guide/case-management',
        'user-guide/state-help',
        'user-guide/faq',
      ],
    },
  ],
  partnersCourts: [
    {
      type: 'category',
      label: 'Partner & court guide (WIP)',
      collapsed: false,
      items: [
        'partners-courts/index',
        'partners-courts/jurisdiction-config',
        'partners-courts/document-checklists',
        'partners-courts/ai-customization',
        'partners-courts/interview-integration',
      ],
    },
  ],
  adminGuide: [
    {
      type: 'category',
      label: 'Admin & deployment (WIP)',
      collapsed: false,
      items: [
        'admin/index',
        'admin/architecture',
        'admin/configuration',
        'admin/deployment',
        'admin/development',
      ],
    },
  ],
};

export default sidebars;
