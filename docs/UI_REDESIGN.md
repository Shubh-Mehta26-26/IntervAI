# IntervAI UI: slate and blue workspace

## Design direction

The application uses cool white surfaces, deep-slate navigation, restrained blue accents, editorial serif headings, and familiar sans-serif controls. Dark mode uses the same semantic palette. No external fonts, animation packages, or image downloads are required.

## Implementation

- `frontend/src/app/design-system.css` owns shared semantic tokens and base components. `editorial.css`, imported last in the root layout, provides the editorial layouts and feature refinements.
- Authentication and dashboard layouts use a small CSS/SVG preparation illustration. It describes existing features and contains no invented activity or scores.
- Role-aware sidebar navigation has expandable Practice, Prepare, and Grow groups. The current route opens its group automatically. The mobile drawer retains focus trapping, Escape dismissal, and focus restoration.
- Workspace search filters local page destinations, supports Ctrl/Cmd+K, and uses a native modal dialog. It does not search or transmit candidate records.
- Shared cards, forms, badges, loading states, empty states, tables, and buttons carry the design through candidate, recruiter, and administration screens.
- Interview controls, the voice orb, live camera, resume parsing, learning plans, career workflows, and API contracts retain their behavior.
- Decorative motion and page transitions respect reduced-motion preferences.

## Verification

- Production webpack build completed successfully with the existing route inventory.
- TypeScript and targeted ESLint checks passed during implementation.
- Authenticated HTTP checks passed for 15 candidate pages, recruiter and administrator workspaces, and the interview/resume/job/progress API proxy routes.
- Browser checks covered sign-in, dashboard, learning plans, light/dark mode, navigation groups, search filtering and navigation, mobile drawer dismissal, focus restoration, and the keyboard search shortcut.
- Responsive browser inspection used a 390 x 844 viewport, including a document-width check with no horizontal page overflow.

## Scope of verification

The UI pass does not claim a new end-to-end test of physical camera/microphone devices, AI providers, or every dynamic detail workflow. Authentication and page smoke checks used disposable local accounts; real candidate data was not edited.
