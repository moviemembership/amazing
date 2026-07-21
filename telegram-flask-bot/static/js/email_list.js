const body = document.body;
const deleteForm = document.getElementById("deleteForm");
const startDeleteButton =
    document.getElementById("startDeleteButton");
const cancelDeleteButton =
    document.getElementById("cancelDeleteButton");
const prepareDeleteButton =
    document.getElementById("prepareDeleteButton");

const noticeModal =
    document.getElementById("noticeModal");
const noticeTitle =
    document.getElementById("noticeTitle");
const noticeMessage =
    document.getElementById("noticeMessage");
const closeNoticeButton =
    document.getElementById("closeNoticeButton");

const confirmModal =
    document.getElementById("confirmModal");
const confirmDeleteMessage =
    document.getElementById("confirmDeleteMessage");
const cancelConfirmButton =
    document.getElementById("cancelConfirmButton");
const confirmDeleteButton =
    document.getElementById("confirmDeleteButton");

function selectedCheckboxes() {
    return Array.from(
        document.querySelectorAll(
            ".parent-checkbox:checked"
        )
    );
}

function clearSelections() {
    document.querySelectorAll(
        ".parent-checkbox"
    ).forEach(function (checkbox) {
        checkbox.checked = false;
    });
}

function showNoticeModal(title, message) {
    noticeTitle.textContent = title;
    noticeMessage.textContent = message;
    noticeModal.classList.add("show");
}

function closeNoticeModal() {
    noticeModal.classList.remove("show");
}

startDeleteButton.addEventListener(
    "click",
    function () {
        body.classList.add("delete-mode");
    }
);

cancelDeleteButton.addEventListener(
    "click",
    function () {
        clearSelections();
        body.classList.remove("delete-mode");
    }
);

prepareDeleteButton.addEventListener(
    "click",
    function () {
        const selected = selectedCheckboxes();

        if (selected.length === 0) {
            showNoticeModal(
                "Nothing selected",
                "Please select at least one parent email."
            );
            return;
        }

        confirmDeleteMessage.textContent =
            "Delete " +
            selected.length +
            " selected parent email(s)? " +
            "All replacement emails below them will also be deleted.";

        confirmModal.classList.add("show");
    }
);

closeNoticeButton.addEventListener(
    "click",
    closeNoticeModal
);

cancelConfirmButton.addEventListener(
    "click",
    function () {
        confirmModal.classList.remove("show");
    }
);

confirmDeleteButton.addEventListener(
    "click",
    function () {
        deleteForm.submit();
    }
);

noticeModal.addEventListener(
    "click",
    function (event) {
        if (event.target === noticeModal) {
            closeNoticeModal();
        }
    }
);

confirmModal.addEventListener(
    "click",
    function (event) {
        if (event.target === confirmModal) {
            confirmModal.classList.remove("show");
        }
    }
);

const noticeMessages = {
    none_selected: [
        "Nothing selected",
        "Please select at least one parent email."
    ],
    deleted: [
        "Deleted",
        "The selected parent accounts and their replacements were deleted."
    ],
    added: [
        "Emails added",
        "The parent email accounts were added successfully."
    ],
    replacement_added: [
        "Replacement added",
        "The replacement account was attached successfully."
    ]
};

if (
    window.EMAIL_NOTICE &&
    noticeMessages[window.EMAIL_NOTICE]
) {
    window.addEventListener("load", function () {
        const message =
            noticeMessages[window.EMAIL_NOTICE];

        showNoticeModal(
            message[0],
            message[1]
        );
    });
}

document.querySelectorAll(
    ".copy-email-button"
).forEach(function (button) {

    button.addEventListener(
        "click",
        async function () {

            const copyType =
                button.dataset.copyType;

            const email =
                button.dataset.email;

            const password =
                button.dataset.password;

            const copyText =
                copyType +
                "\n\n" +
                email +
                "\n" +
                "password: " +
                password +
                "\n\n" +
                "Guide to login: " +
                "https://mantapnet.my/instructions" +
                "\n\n" +
                "Get code at " +
                "https://mantapnet.my/get-code";

            try {
                await navigator.clipboard.writeText(
                    copyText
                );

                const originalText =
                    button.textContent;

                button.textContent = "Copied";

                setTimeout(function () {
                    button.textContent =
                        originalText;
                }, 1200);

            } catch (error) {
                const textarea =
                    document.createElement("textarea");

                textarea.value = copyText;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";

                document.body.appendChild(
                    textarea
                );

                textarea.select();

                document.execCommand("copy");

                textarea.remove();

                const originalText =
                    button.textContent;

                button.textContent = "Copied";

                setTimeout(function () {
                    button.textContent =
                        originalText;
                }, 1200);
            }
        }
    );
});
