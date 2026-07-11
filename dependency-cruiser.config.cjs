/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: 'no-circular-dependencies',
      severity: 'error',
      from: {},
      to: { circular: true }
    },
    {
      name: 'no-unresolved-local-imports',
      severity: 'error',
      from: { path: '^src' },
      to: { couldNotResolve: true, pathNot: '^node:' }
    },
    {
      name: 'features-do-not-depend-on-routes',
      severity: 'error',
      from: { path: '^src/features/' },
      to: { path: '^src/routes/' }
    },
    {
      name: 'features-do-not-depend-on-app',
      severity: 'error',
      from: { path: '^src/features/' },
      to: {
        path: '^src/app/',
        pathNot: '^src/app/(i18nContext|shellUrl)\\.tsx?$'
      }
    },
    {
      name: 'entities-stay-below-features-and-routes',
      severity: 'error',
      from: { path: '^src/entities/' },
      to: { path: '^src/(features|routes|app)/' }
    },
    {
      name: 'design-is-independent',
      severity: 'error',
      from: { path: '^src/design/' },
      to: { path: '^src/(app|routes|features|entities|data|visualization)/' }
    },
    {
      name: 'data-is-ui-independent',
      severity: 'error',
      from: { path: '^src/data/' },
      to: { path: '^src/(app|routes|features|entities|design|visualization)/' }
    },
    {
      name: 'routes-do-not-depend-on-app',
      severity: 'error',
      from: { path: '^src/routes/' },
      to: { path: '^src/app/' }
    },
    {
      name: 'visualization-spec-is-renderer-and-react-free',
      severity: 'error',
      from: { path: '^src/visualization/spec/' },
      to: { path: '(^react$|^react/|^echarts($|/)|src/visualization/(renderer|react)/)' }
    },
    {
      name: 'visualization-fixtures-are-ui-free',
      severity: 'error',
      from: { path: '^src/visualization/fixtures/' },
      to: { path: '(^react$|^react/|^echarts($|/)|src/visualization/(renderer|react|lab)/)' }
    },
    {
      name: 'echarts-is-confined-to-visualization-renderer',
      severity: 'error',
      from: { path: '^src/', pathNot: '^src/visualization/renderer/' },
      to: { path: '^echarts($|/)' }
    },
    {
      name: 'data-contracts-are-react-and-fixture-free',
      severity: 'error',
      from: { path: '^src/data/contracts/' },
      to: { path: '(^react$|^react/|src/(fixtures|test-fixtures)/)' }
    }
  ],
  options: {
    doNotFollow: { path: 'node_modules' },
    tsConfig: { fileName: 'tsconfig.json' },
    enhancedResolveOptions: {
      extensions: ['.js', '.jsx', '.ts', '.tsx', '.d.ts']
    },
    reporterOptions: {
      text: { highlightFocused: true }
    }
  }
};
