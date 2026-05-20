// Home hero slider: rotates the active hero background image every few seconds.

const slides =
document.querySelectorAll(".hero-slide");

let currentSlide = 0;

function changeSlide(){

    if(slides.length === 0) return;

    slides[currentSlide]
    .classList.remove("active");

    currentSlide =
    (currentSlide + 1)
    % slides.length;

    slides[currentSlide]
    .classList.add("active");

}

setInterval(changeSlide,4000);


// Delete confirmation: shows a SweetAlert prompt, then submits a POST form with CSRF.

function deleteListing(id){

    Swal.fire({

        title:'Delete Listing?',

        text:'This listing will be removed.',

        icon:'warning',

        showCancelButton:true,

        confirmButtonColor:'#ef4444',

        confirmButtonText:'Delete'

    }).then((result)=>{

        if(result.isConfirmed){

            const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
            const form = document.createElement("form");
            form.method = "POST";
            form.action = "/delete/" + id;

            const input = document.createElement("input");
            input.type = "hidden";
            input.name = "_csrf_token";
            input.value = token;

            form.appendChild(input);
            document.body.appendChild(form);
            form.submit();

        }

    });

}
