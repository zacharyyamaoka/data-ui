/* The case's page hook: a file a media cell takes stays a blob: URL in this page. A real host stores it and answers with
   its own url (data-ui keeps no bytes, docs/CONTRACT.md §37). */
const el = document.querySelector('data-views');
el.acceptFile = async ({ file }) => ({
  ok: true,
  attachment: { url: URL.createObjectURL(file), kind: file.type.startsWith('video/') ? 'video' : 'image', name: file.name },
});
