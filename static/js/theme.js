const lightThemeCSS = "/static/css/foundation-light.min.css";
const darkThemeCSS = "/static/css/foundation-dark.min.css";
var toDark, toLight;

$(document).ready(() => {
    toDark = document.querySelector('.to-dark');
    toLight = document.querySelector('.to-light');

    document.querySelectorAll('.theme')
        .forEach( button => button.addEventListener('click', toggleTheme) )

    // Fetch default theme from localStorage and apply it.
    var theme = localStorage.getItem("data-theme");
    if (theme === 'dark') toggleTheme();
    else toLight.style.display = "none";
});


function toggleTheme() {
    document.documentElement.toggleAttribute("dark")
    const theme = document.querySelector("#theme-link");
    if (theme.getAttribute("href") == lightThemeCSS) {
        theme.href = darkThemeCSS;
        toDark.style.display = "none";
        toLight.style.display = '';
        localStorage.setItem("data-theme", "dark");
    }
    else {
        theme.href = lightThemeCSS;
        toDark.style.display = '';
        toLight.style.display = "none";
        localStorage.setItem("data-theme", "light");
    }
}
