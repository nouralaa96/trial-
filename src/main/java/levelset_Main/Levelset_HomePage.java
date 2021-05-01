package levelset_Main;

import org.openqa.selenium.By;
import org.testng.Assert;

import actions.UIActions;

public class Levelset_HomePage { 
	//variables
   // private final WebDriver driverhomepage   ;
    // Constructor method
     /* public Levelset_HomePage (WebDriver driver1) {

       this.driverhomepage = driver1 ;
    }   */
      // locators  
       public  By findstring = By.xpath("//*[@class=\"text-lg\"]") ;
       public By create_a_document = By.xpath("//a[@class=\"btn btn-info btn-outline mob-dropdown-btn\"]") ;
	   // keywords 
      
       UIActions UIobject ; 
       
  public void navigateLevelset() {   
	  
	  UIobject =new  UIActions();  
       By webpath =By.xpath("//h1[text()='Get paid faster.']") ;
       UIobject.navigateToAnyPAge("https://www.levelset.com/", webpath );
 //new UIActions(driverhomepage).navigateToAnyPAge("https://www.levelset.com/", By.xpath("h1[text()=\\\"Get paid faster.\\\"]") );
      
                                             }  
  
          
 
  
  
   public String check_navigaton_bysearch() {   // a unique string to check that if navigate yo the write website.
	   
/*   String checkhomepage  =  driverhomepage.findElement(findstring).getText() ;
	        return checkhomepage ; */ 
	 String checkpage = new UIActions().check_navigaton_tothe_rigthPage(findstring) ;
                      return checkpage;
}  
      public void  checkclickable_create_a_document() {
  
 // UIobject =new  UIActions(driverhomepage); // before declaring driver as static i should send driver for each class constructor 
    	  UIobject =new  UIActions(); 
        boolean checkclicakble =UIobject.checkclickable_Button(create_a_document) ;
    	              
             Assert.assertTrue(checkclicakble );
          
    	/* //     create wait object to check button is clickable .
		WebDriverWait wait = new WebDriverWait(driverhomepage, 15);
	     WebElement element =wait.until(ExpectedConditions.elementToBeClickable(create_a_document));  
	    //    System.out.println("------------------"+element); 
	     // to confim that elementToBeClickable return webelement which mean button is clickable
		          if(element!=null) { 
		        	  driverhomepage.findElement(create_a_document).click();
		        	  return true ;  
		          }else
			     	return false; */
		          
    }
   }  



/* boolean	 create_a_documentbutton= driverhomepage.findElement(create_a_document).isDisplayed();
if(create_a_documentbutton ==true )
{
	driverhomepage.findElement(create_a_document).click();
}  */  

