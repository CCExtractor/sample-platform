$(document).ready(() => {
    $('.theme-toggle i.theme').on('click', toggleTheme);
    // Toggle Icon Not Shown Until Page Completely Loads

    // Fetch default theme from localStorage and apply it.
    const theme = localStorage.getItem("data-theme");
    if (theme === 'dark') toggleTheme();
    else $('.theme-toggle i.to-dark').removeClass('hidden');
});


function toggleTheme() {
    document.documentElement.toggleAttribute("dark");
    const theme = document.querySelector("#theme-link");
    
    const toDark = $('.theme-toggle i.to-dark');
    const toLight = $('.theme-toggle i.to-light');
    // Not Allowing User to Toggle Theme Again Before This Gets Completed. 
    toDark.addClass('hidden')   
    toLight.addClass('hidden')
    
    const lightThemeCSS = "/static/css/foundation-light.min.css";
    const darkThemeCSS = "/static/css/foundation-dark.min.css";

    if (theme.getAttribute("href") == lightThemeCSS) {
        theme.href = darkThemeCSS;
        localStorage.setItem("data-theme", "dark");
        toLight.removeClass('hidden')
    }
    else {
        theme.href = lightThemeCSS;
        localStorage.setItem("data-theme", "light");
        toDark.removeClass('hidden')
    }
}
