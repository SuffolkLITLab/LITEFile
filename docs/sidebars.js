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
        'partners-courts/customization',
        'partners-courts/jurisdiction-config',
        'partners-courts/email-review',
        'partners-courts/maintained-data',
        'partners-courts/filing-availability',
        'partners-courts/document-checklists',
        'partners-courts/document-finder',
        'partners-courts/ai-customization',
        'partners-courts/interview-integration',
        'partners-courts/reporting',
        'partners-courts/maintenance',
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
        'admin/filing-code-operations',
        'admin/staff-onboarding',
        'admin/service-maintenance',
        'admin/documentation-review',
        'admin/development',
      ],
    },
  ],
};

export default sidebars;
