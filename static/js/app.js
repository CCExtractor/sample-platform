/*global $, Foundation */
$(document).foundation();

var CIPlatform = {};
CIPlatform.errorHandler = (function () {
    'use strict';
    var instance, createContent, showErrorInElement, showErrorInList,
        showFormErrors, clearFormErrors, showErrorInPopup, registerListeners;

    // Init functions
    createContent = function (errors, isFormError) {
        var content, field, idx;

        isFormError = isFormError || false;
        content = "";
        if (errors.length === 1) {
            content = errors[0];
        } else {
            content = "The next errors occurred:<br><ul>";
            if (isFormError) {
                for (field in errors) {
                    if (errors.hasOwnProperty(field)) {
                        for (idx = 0; idx < errors[field].length; idx++) {
                            content += "<li>" + errors[field][idx] + "</li>";
                        }
                    }
                }
            } else {
                for (idx = 0; idx < errors.length; idx++) {
                    content += "<li>" + errors[idx] + "</li>";
                }
            }
            content += "</ul>";
        }
        window.console.log(errors);

        return content;
    };
    showErrorInElement = function (jQueryElement, errors, fadeOut) {
        fadeOut = fadeOut || 0;
        jQueryElement.show().html(createContent(errors));
        if (fadeOut > 0) {
            setTimeout(function () { jQueryElement.fadeOut(1000); }, fadeOut);
        }
    };
    showErrorInList = function (jQueryElement, errors) {
        jQueryElement.empty();
        errors.forEach(function (elm) {
            jQueryElement.append("<li>" + elm + "</li>");
        });
        $("#errorMessage").removeClass("hide");
    };
    showFormErrors = function(jQueryElement, formName, errors, prefix) {
        var error, field, form;

        prefix = '' || prefix;
        form = document.forms[formName];
        // Show error message
        $(form.getElementsByClassName('form-errors')[0]).show();
        // Mark fields
        for (error in errors) {
            if (errors.hasOwnProperty(error)) {
                field = form[prefix + error];
                if(field !== undefined){
                    $(field).addClass('is-invalid-input').attr('aria-describedby',field.id + '_error');
                    $("#" + field.id + "_error").html(errors[error].join(', ')+'.').addClass('is-visible');
                    $('label[for=' + field.id + ']').addClass('is-invalid-label');
                }
            }
        }
        // Clear ajax loader
        jQueryElement.html('');
    };
    clearFormErrors = function(formName) {
        var form, field, idx;

        form = document.forms[formName];
        $(form.getElementsByClassName('form-errors')[0]).hide();
        // Reset fields
        for (idx = 0; idx < form.elements.length; idx++) {
            field = form.elements[idx];
            $(field).removeClass('is-invalid-input');
            if($("#"+field.id+"_help_text").length > 0){
                $(field).attr('aria-describedby', field.id + '_help_text');
            }
            $("#" + field.id + "_error").html('').removeClass('is-visible');
            if (field.id.length > 0) {
                $('label[for=' + field.id + ']').removeClass('is-invalid-label');
            }
        }
    };
    showErrorInPopup = function(errors, needsPageReload) {
        var id, reveal, popup;

        reveal = document.createElement('div');
        id = 'error-popup-'+(new Date()).getTime();
        reveal.setAttribute('id', id);
        reveal.setAttribute('class', 'large reveal');
        reveal.setAttribute('data-reveal', '');
        reveal.innerHTML = createContent(errors, true);
        if (needsPageReload) {
            reveal.innerHTML += '<strong>Please reload the page in order to get the current state for the disabled elements.</strong>';
        }
        reveal.innerHTML +=
            '<button class="close-button" data-close aria-label="Cancel" type="button">' +
            '   <span aria-hidden="true">&times;</span>' +
            '</button>';
        document.body.appendChild(reveal);
        popup = new Foundation.Reveal($('#'+id));
        popup.open();
    };
    registerListeners = function () {
        // We need to add a listener for foundation reveal close events, so we can unregister the reveal instance.
        $(document).on('closed.zf.reveal', function(e){
            $(e.target).foundation('destroy');
        });
    };

    // Create instance & assign functions
    instance = {};
    instance.showErrorInElement = showErrorInElement;
    instance.showErrorInList = showErrorInList;
    instance.showFormErrors = showFormErrors;
    instance.clearFormErrors = clearFormErrors;
    instance.showErrorInPopup = showErrorInPopup;
    instance.registerListeners = registerListeners;

    return instance;
}());
CIPlatform.loadHandler = (function () {
    'use strict';
    var instance, showLoaderInElement, defaultLoaderIcon, defaultLoaderText;

    // Default texts
    defaultLoaderIcon = 'fa-cog';
    defaultLoaderText = 'Please wait while we process the request...';
    // Methods
    showLoaderInElement = function (jQueryElement, loaderIcon, loaderText) {
        loaderIcon = loaderIcon || defaultLoaderIcon;
        loaderText = loaderText || defaultLoaderText;
        jQueryElement.html('<i class="fa fa-spin ' + loaderIcon + '"></i> ' + loaderText);
    };
    // Create instance & assign functions
    instance = {};
    instance.showLoaderInElement = showLoaderInElement;

    return instance;
}());

$(document).ready(function(){
    CIPlatform.errorHandler.registerListeners();
});