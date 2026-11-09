// Logo Mysa : le fichier fourni (fond détouré), avec une variante où le texte passe en clair pour
// rester lisible sur fond sombre (le dégradé bleu du toit, lui, ne change pas). La bonne variante
// s'affiche seule grâce à styles.css / theme-dark.css : pas de logique ici.
export default function Logo({ height = 40 }) {
  const base = import.meta.env.BASE_URL;
  return (
    <span className="logo" style={{ height }}>
      <img className="logo-img logo-img-light" src={`${base}mysa-logo.png`} height={height} alt="Mysa" />
      <img className="logo-img logo-img-dark" src={`${base}mysa-logo-dark.png`} height={height} alt="Mysa" />
    </span>
  );
}
